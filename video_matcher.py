"""
video_matcher.py — Verifies that an S3 event clip is a segment of an offline video.

Uses perceptual hashing (pHash) on sampled frames.
Survives re-encoding, resolution changes, bitrate shifts.
Zero cost — only uses ffmpeg + Pillow + imagehash.
"""

import logging
import os
import shutil
import subprocess
import tempfile

import imagehash
from PIL import Image

import config

log = logging.getLogger("matcher")


def _extract_frames(video_path: str, output_dir: str) -> list[str]:
    """Extract frames from video at configured FPS."""
    os.makedirs(output_dir, exist_ok=True)
    pattern = os.path.join(output_dir, "frame_%06d.png")
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-i", video_path,
        "-vf", f"fps={config.MATCH_FPS}",
        "-q:v", "2",
        pattern,
    ], check=True)
    return sorted(
        os.path.join(output_dir, f)
        for f in os.listdir(output_dir)
        if f.startswith("frame_") and f.endswith(".png")
    )


def _compute_phash(image_path: str) -> str:
    """Compute perceptual hash of an image."""
    img = Image.open(image_path)
    return str(imagehash.phash(img, hash_size=config.MATCH_HASH_SIZE))


def _hamming_distance(h1: str, h2: str) -> int:
    """Hamming distance between two hex-encoded hashes."""
    return imagehash.hex_to_hash(h1) - imagehash.hex_to_hash(h2)


def match_clip_to_video(clip_path: str, offline_video_path: str) -> tuple[bool, float]:
    """
    Check if clip_path is a segment of offline_video_path.

    Returns:
        (matched: bool, ratio: float)
        - matched: True if the clip is part of the video
        - ratio: confidence score (0.0 to 1.0)
    """
    tmp_clip = tempfile.mkdtemp(prefix="clip_")
    tmp_video = tempfile.mkdtemp(prefix="video_")

    try:
        clip_frames = _extract_frames(clip_path, tmp_clip)
        video_frames = _extract_frames(offline_video_path, tmp_video)

        if not clip_frames or not video_frames:
            log.warning("  No frames extracted. clip=%d, video=%d",
                        len(clip_frames), len(video_frames))
            return False, 0.0

        clip_hashes = [_compute_phash(f) for f in clip_frames]
        video_hashes = [_compute_phash(f) for f in video_frames]

        n_clip = len(clip_hashes)
        n_video = len(video_hashes)
        best_ratio = 0.0
        tol = 2  # frame tolerance for dropped/duplicated frames

        search_end = max(1, n_video - n_clip + 1 + tol)

        for start in range(search_end):
            for ws in range(max(1, n_clip - tol), n_clip + tol + 1):
                end = start + ws
                if end > n_video:
                    continue
                window = video_hashes[start:end]

                matches = 0
                for ci, ch in enumerate(clip_hashes):
                    pos = int(ci * len(window) / n_clip)
                    lo = max(0, pos - tol)
                    hi = min(len(window), pos + tol + 1)
                    for wi in range(lo, hi):
                        if _hamming_distance(ch, window[wi]) <= config.MATCH_HAMMING_THRESHOLD:
                            matches += 1
                            break

                ratio = matches / n_clip
                if ratio > best_ratio:
                    best_ratio = ratio

            if best_ratio >= config.MATCH_MIN_RATIO:
                break

        matched = best_ratio >= config.MATCH_MIN_RATIO
        return matched, best_ratio

    finally:
        shutil.rmtree(tmp_clip, ignore_errors=True)
        shutil.rmtree(tmp_video, ignore_errors=True)
