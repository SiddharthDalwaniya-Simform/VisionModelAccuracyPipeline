"""
run.py — Main entry point. Run this to start the test.

Usage:
    python run.py                  Full test run
    python run.py --dry-run        Just discover videos + create Excel skeleton
    python run.py --skip-services  Skip starting HTTP server and tunnel
                                   (use if you already started them manually)

Edit config.py FIRST, then run this.
"""

import argparse
import logging
import os
import shutil
import tempfile
import time
from datetime import datetime

import config
from stream_manager import StreamManager
from s3_checker import S3EventChecker
from video_matcher import match_clip_to_video
from excel_report import ExcelReport
from video_utils import get_duration, discover_videos

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
log = logging.getLogger("main")


def run(skip_services=False, dry_run=False):

    # ---- Discover videos ----
    videos = discover_videos(config.VIDEO_DIR)
    if not videos:
        log.error("No videos found in %s", config.VIDEO_DIR)
        return
    log.info("Found %d videos in %s", len(videos), config.VIDEO_DIR)

    total = len(videos)
    passed = 0
    missed = 0
    mismatched = 0

    # ---- Initialize components ----
    stream = StreamManager()
    s3 = S3EventChecker()
    excel = ExcelReport()

    # ---- Prepare HLS output directory ----
    stream.prepare_output_dir()

    # ---- Start services (HTTP server + Cloudflare Tunnel) ----
    if dry_run:
        log.info("DRY RUN — skipping services, streaming, and S3 checks.")
    elif skip_services:
        log.info("Skipping service startup (--skip-services).")
        log.info("Make sure HTTP server and Cloudflare Tunnel are already running!")
    else:
        stream.start_services()

    try:
        for i, video_path in enumerate(videos, 1):
            video_name = os.path.basename(video_path)
            duration = get_duration(video_path)

            log.info("")
            log.info("=" * 60)
            log.info("[%d/%d] %s (%.1fs)", i, total, video_name, duration)
            log.info("=" * 60)

            # ---- Dry run: just populate Excel with video info ----
            if dry_run:
                excel.add_result(
                    i, video_name, duration,
                    False, "", None, 0.0, "Dry run — not streamed",
                )
                missed += 1
                continue

            # ---- 1. Write video to playlist and start ffmpeg ----
            stream.clean_between_videos()
            stream.write_playlist(video_path)
            stream_start_time = datetime.utcnow()
            stream.start_ffmpeg()

            # ---- 2. Wait for video to finish playing ----
            log.info("  Waiting %.0fs for video to play…", duration)
            time.sleep(duration)

            # ---- 3. Wait extra buffer for ML pipeline ----
            buffer = duration * (config.WAIT_MULTIPLIER - 1)
            if buffer > 0:
                log.info("  Waiting %.0fs more for ML pipeline…", buffer)
                time.sleep(buffer)

            # ---- 4. Check database for events ----
            log.info("  Checking database (polling up to %.0fs)…", config.EXTRA_WAIT)
            new_events = s3.check_for_events(
                stream_start_time=stream_start_time,
                timeout=config.EXTRA_WAIT,
            )

            # ---- 5. Process results ----
            event_received = len(new_events) > 0
            s3_link = ""
            match_result = None
            match_ratio = 0.0
            notes = ""

            if event_received:
                s3_key = new_events[0]["video_s3_key"]
                s3_link = f"s3://{config.S3_BUCKET}/{s3_key}"
                log.info("  Event found: %s", s3_link)

                confidence = new_events[0].get("match_confidence", "")
                if confidence:
                    notes = f"confidence={confidence}"

                if len(new_events) > 1:
                    notes += f" ({len(new_events)} events; verified first)"

                # Download and pHash verify
                tmp_dir = tempfile.mkdtemp(prefix="event_")
                try:
                    local_clip = s3.download_clip(s3_key, tmp_dir)
                    match_result, match_ratio = match_clip_to_video(
                        local_clip, video_path
                    )

                    if match_result:
                        log.info("  ✔ MATCH (ratio=%.2f)", match_ratio)
                        passed += 1
                    else:
                        log.info("  ✘ MISMATCH (ratio=%.2f)", match_ratio)
                        mismatched += 1
                        notes += f" ratio={match_ratio:.2f}"
                finally:
                    shutil.rmtree(tmp_dir, ignore_errors=True)
            else:
                log.info("  ✘ NO EVENT")
                missed += 1
                notes = "Model did not detect shoplifting"

            # ---- 6. Update Excel ----
            excel.add_result(
                i, video_name, duration, event_received,
                s3_link, match_result, match_ratio, notes,
            )

            # ---- 7. Stop ffmpeg, ready for next video ----
            stream.stop_ffmpeg()

        # ---- Final summary ----
        excel.add_summary(total, passed, missed, mismatched)

        log.info("")
        log.info("=" * 60)
        log.info("  COMPLETE")
        log.info("=" * 60)
        log.info("  Total:      %d", total)
        log.info("  Passed:     %d", passed)
        log.info("  No Event:   %d", missed)
        log.info("  Mismatch:   %d", mismatched)
        log.info("  Detection:  %.1f%%", passed / total * 100 if total else 0)
        log.info("  Report:     %s", config.OUTPUT_EXCEL)
        log.info("=" * 60)

    finally:
        stream.stop_all()
        s3.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Shoplifting Detection Test")
    p.add_argument(
        "--skip-services", action="store_true",
        help="Don't start HTTP server and tunnel (if already running manually)",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="Discover videos and create Excel without streaming",
    )
    args = p.parse_args()

    run(skip_services=args.skip_services, dry_run=args.dry_run)
