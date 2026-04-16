"""
run.py — Main entry point. Run this to start the test.

Usage:
    python run.py                  Full test run (defaults to dev)
    python run.py --env stage      Run against staging environment
    python run.py --env prod       Run against production environment
    python run.py --dry-run        Just discover videos + create Excel skeleton
    python run.py --skip-services  Skip starting HTTP server and tunnel
                                   (use if you already started them manually)

You can also set the ENV environment variable instead of --env:
    set ENV=stage && python run.py
"""

import argparse
import logging
import os
import shutil
import sys
import tempfile
import time
from datetime import datetime

# --- Parse --env and --log early so config + logging are set up correctly ---
_pre_parser = argparse.ArgumentParser(add_help=False)
_pre_parser.add_argument("--env", default=None)
_pre_parser.add_argument("--log", default=None, choices=["debug", "normal", "none"])
_pre_args, _ = _pre_parser.parse_known_args()
if _pre_args.env:
    os.environ["ENV"] = _pre_args.env

import config  # noqa: E402  (must come after ENV is set)

# --log flag overrides LOG_LEVEL from config
if _pre_args.log:
    config.LOG_LEVEL = _pre_args.log

from stream_manager import StreamManager
from s3_checker import S3EventChecker
from video_matcher import match_clip_to_video
from excel_report import ExcelReport
from video_utils import get_duration, discover_videos

# --- Apply LOG_LEVEL from config and set up handlers ---
_LOG_LEVEL_MAP = {"debug": logging.DEBUG, "normal": logging.ERROR, "none": None}
_log_level = _LOG_LEVEL_MAP.get(getattr(config, "LOG_LEVEL", "debug").lower(), logging.DEBUG)

_fmt = logging.Formatter("%(asctime)s  %(levelname)-8s  %(name)s  %(message)s")

# Ensure logs/ directory exists and open a timestamped file for this run
_logs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(_logs_dir, exist_ok=True)
_run_ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
_log_filename = os.path.join(_logs_dir, f"{_run_ts}_{config.ENV}.log")

_file_handler = logging.FileHandler(_log_filename, encoding="utf-8")
_file_handler.setFormatter(_fmt)

_console_handler = logging.StreamHandler()
_console_handler.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-8s  %(message)s"))

_root = logging.getLogger()
_root.handlers.clear()
_root.addHandler(_file_handler)
_root.addHandler(_console_handler)

if _log_level is None:
    # "none" — suppress terminal output; still write errors to file
    _console_handler.setLevel(logging.CRITICAL + 1)  # effectively silent
    _file_handler.setLevel(logging.DEBUG)
    _root.setLevel(logging.DEBUG)
else:
    _root.setLevel(_log_level)
    _file_handler.setLevel(_log_level)
    _console_handler.setLevel(_log_level)
    # Suppress verbose third-party output in non-debug mode
    if _log_level > logging.DEBUG:
        for _lib in ("paramiko", "sshtunnel", "boto3", "botocore", "urllib3", "s3transfer"):
            logging.getLogger(_lib).setLevel(logging.ERROR)

log = logging.getLogger("main")
log.info("Log file: %s", _log_filename)


def run(skip_services=False, dry_run=False):

    run_start_time = time.time()

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
    excel = ExcelReport()

    # Connect to DB/S3 (skipped for dry-run — preflight handles it below)
    s3 = None
    conn_error = None
    if not dry_run:
        try:
            s3 = S3EventChecker()
        except Exception as exc:
            conn_error = str(exc)
            log.error("Failed to establish DB/SSH connection: %s", exc)

    # ---- Prepare HLS output directory ----
    stream.prepare_output_dir()

    # ---- Start services (HTTP server + Cloudflare Tunnel) ----
    preflight_ok = True
    if dry_run:
        log.info("DRY RUN — skipping streaming. Running preflight connection check…")
        _pflight = None
        try:
            _pflight = S3EventChecker()
            preflight_ok = _pflight.test_connections()
        except Exception as exc:
            log.error("Preflight connection error: %s", exc)
            preflight_ok = False
        finally:
            if _pflight:
                _pflight.close()
        if not preflight_ok:
            log.error("Preflight check failed. Excel will show CONN FAILED for all videos.")
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

            # ---- Dry run: populate Excel (with preflight result) ----
            if dry_run:
                if not preflight_ok:
                    excel.add_result(
                        i, video_name, duration,
                        False, "", None, 0.0, "DB connection failed — see logs",
                        force_status="CONN FAILED",
                    )
                else:
                    excel.add_result(
                        i, video_name, duration,
                        False, "", None, 0.0, "Dry run — preflight passed",
                    )
                missed += 1
                continue

            # ---- Real run: mark all videos as CONN FAILED if DB unavailable ----
            if conn_error:
                excel.add_result(
                    i, video_name, duration,
                    False, "", None, 0.0, f"DB connection failed: {conn_error[:80]}",
                    force_status="CONN FAILED",
                )
                missed += 1
                continue

            # ---- 1. Write video to playlist and start ffmpeg ----
            stream.clean_between_videos()
            stream.write_playlist(video_path)
            stream_start_time = datetime.utcnow()
            stream.start_ffmpeg()

            buffer = duration * (config.WAIT_MULTIPLIER - 1)
            # ---- 2. Poll database while the video is playing ----
            log.info("  Checking database while video plays (up to %.0fs)…", duration)
            new_events = s3.check_for_events(
                stream_start_time=stream_start_time,
                timeout=duration,
                stop_on_first_event=False,
            )

            # ---- 3. If playback had no events, continue through cooldown ----
            if new_events:
                log.info("  Event detected during playback — skipping cooldown period.")
            elif buffer > 0:
                log.info("  No events during playback. Checking through cooldown for %.0fs…", buffer)
                new_events = s3.check_for_events(
                    stream_start_time=stream_start_time,
                    timeout=buffer,
                )

            # ---- 4. Process results ----
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

            # ---- 5. Update Excel ----
            excel.add_result(
                i, video_name, duration, event_received,
                s3_link, match_result, match_ratio, notes,
            )

            # ---- 6. Stop ffmpeg, ready for next video ----
            stream.stop_ffmpeg()

        # ---- Final summary ----
        elapsed = time.time() - run_start_time
        minutes, seconds = divmod(int(elapsed), 60)
        hours, minutes = divmod(minutes, 60)
        exec_time_str = "%dh %02dm %02ds" % (hours, minutes, seconds)

        excel.add_summary(total, passed, missed, mismatched, execution_time=exec_time_str)

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
        log.info("  Time:       %s", exec_time_str)
        log.info("=" * 60)

    finally:
        stream.stop_all()
        if s3:
            s3.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Shoplifting Detection Test")
    p.add_argument(
        "--env", default=os.environ.get("ENV", "dev"),
        choices=config.VALID_ENVS,
        help="Target environment (default: dev). Overrides ENV variable.",
    )
    p.add_argument(
        "--log", default=None,
        choices=["debug", "normal", "none"],
        help="Log level (default: from config LOG_LEVEL). debug=everything, normal=errors only, none=silent.",
    )
    p.add_argument(
        "--skip-services", action="store_true",
        help="Don't start HTTP server and tunnel (if already running manually)",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="Discover videos and create Excel without streaming",
    )
    args = p.parse_args()

    log.info("Environment: %s", config.ENV)
    run(skip_services=args.skip_services, dry_run=args.dry_run)
