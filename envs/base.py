# ============================================================
# BASE CONFIG — Shared defaults across all environments
# ============================================================
# Environment-specific files (dev.py, stage.py, prod.py) import
# these and override only what differs per environment.

# --- YOUR VIDEOS ---
VIDEO_DIR = r"changeMe"

# --- YOUR STREAMING SETUP ---
PLAYLIST_PATH = "playlist.txt"
HLS_OUTPUT_DIR = r"changeMe"
HTTP_PORT = 8080
TUNNEL_STARTUP_WAIT = 8.0
SETTLE_TIME = 5.0

# --- TIMING ---
WAIT_MULTIPLIER = 2.0
EXTRA_WAIT = 30.0
POLL_INTERVAL = 10.0

# --- AWS ---
# Set per-environment in dev.py / stage.py / prod.py.
# Leave as None to fall back to ~/.aws/credentials or instance profile.
AWS_ACCESS_KEY_ID = None
AWS_SECRET_ACCESS_KEY = None
AWS_REGION = "changeMe"

# --- LOGGING ---
# Controls how much is printed to the terminal during a run.
#   "debug"  → every minor step is logged (INFO + DEBUG messages)
#   "normal" → only errors are shown (ERROR and above)
#   "none"   → nothing is printed at all
LOG_LEVEL = "normal"

# --- OUTPUT ---
OUTPUT_EXCEL = "test_results.xlsx"

# --- VIDEO MATCHER ---
MATCH_FPS = 1.0
MATCH_HASH_SIZE = 16
MATCH_HAMMING_THRESHOLD = 12
MATCH_MIN_RATIO = 0.75
