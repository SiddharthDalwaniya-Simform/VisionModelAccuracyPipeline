# ============================================================
# BASE CONFIG — Shared defaults across all environments
# ============================================================
# Environment-specific files (dev.py, stage.py, prod.py) import
# these and override only what differs per environment.
#
# HOW TO USE:
#   1. Copy this file to base.py  (remove the .example part)
#   2. Fill in the values marked CHANGE_ME
#   3. Do the same for dev.example.py, stage.example.py, prod.example.py
# ============================================================

# --- YOUR VIDEOS ---
VIDEO_DIR = r"CHANGE_ME"
# Full path to the folder containing your offline test videos.
# Example: r"C:\Users\john\test_videos"

# --- YOUR STREAMING SETUP ---
PLAYLIST_PATH = "playlist.txt"
HLS_OUTPUT_DIR = r"CHANGE_ME"
# Folder where ffmpeg writes HLS segments. Example: r"C:\temp_stream"
HLS_PLAYLIST_NAME = "cctv.m3u8"
HTTP_PORT = 8080
TUNNEL_STARTUP_WAIT = 8.0
SETTLE_TIME = 5.0

# Use transcoding for broad VLC/HLS compatibility (MOV/MP4 inputs may fail with copy mode).
HLS_TRANSCODE = True

# --- TIMING ---
WAIT_MULTIPLIER = 2.0
# Total poll time = video_duration × this. Increase for slow ML pipelines.
EXTRA_WAIT = 30.0
# Additional seconds to keep polling after video ends.
POLL_INTERVAL = 10.0
# How often to poll the database (seconds).

# --- AWS ---
# Set per-environment in dev.py / stage.py / prod.py.
# Leave as None to fall back to ~/.aws/credentials or instance profile.
AWS_ACCESS_KEY_ID = None
AWS_SECRET_ACCESS_KEY = None
AWS_REGION = "CHANGE_ME"
# Example: "eu-central-1"

# --- LOGGING ---
# Controls how much is printed to the terminal during a run.
#   "debug"  → every minor step is logged (INFO + DEBUG messages)
#   "normal" → only errors are shown (ERROR and above)
#   "none"   → nothing is printed at all
LOG_LEVEL = "debug"

# --- OUTPUT ---
OUTPUT_EXCEL = "test_results.xlsx"

# --- VIDEO MATCHER ---
# Set to False to skip downloading and matching S3 clips against local videos.
ENABLE_VIDEO_MATCHING = False
MATCH_FPS = 1.0
MATCH_HASH_SIZE = 16
MATCH_HAMMING_THRESHOLD = 12
MATCH_MIN_RATIO = 0.75
