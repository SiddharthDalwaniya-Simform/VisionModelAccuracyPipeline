"""
video_utils.py — Video utility functions.
"""

import subprocess
from pathlib import Path


def get_duration(video_path: str) -> float:
    """Get video duration in seconds using ffprobe."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "csv=p=0",
        video_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return float(result.stdout.strip())


def discover_videos(directory: str) -> list[str]:
    """Find all video files in a directory, sorted by name."""
    video_exts = {".mp4", ".mkv", ".avi", ".mov", ".ts", ".flv", ".webm"}
    return sorted(
        str(p) for p in Path(directory).rglob("*")
        if p.suffix.lower() in video_exts
    )


def read_playlist(playlist_path: str) -> list[str]:
    """Read video paths from an existing playlist.txt file."""
    import os
    videos = []
    with open(playlist_path, "r") as f:
        for line in f:
            line = line.strip()
            if line.startswith("file "):
                path = line.split("'")[1] if "'" in line else line[5:]
                if os.path.exists(path):
                    videos.append(path)
    return videos
