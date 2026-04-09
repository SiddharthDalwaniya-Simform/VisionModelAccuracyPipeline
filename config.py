# ============================================================
# CONFIG.PY — The ONLY file you need to edit
# ============================================================

# --- YOUR VIDEOS ---
VIDEO_DIR = r""
# The folder containing your 100 offline test videos.
# Example: r"C:\Users\john\shoplifting_test_videos"

# --- DATABASE (PostgreSQL via SSH Tunnel) ---
DB_HOST = ""
DB_PORT = 
DB_NAME = ""
DB_USER = ""
DB_PASSWORD = ""
# Connection details for the PostgreSQL database where ML writes events.
# DB_HOST is the host as seen from INSIDE the SSH tunnel (e.g. 127.0.0.1 or RDS endpoint).

# --- SSH TUNNEL (required to reach the database) ---
SSH_TUNNEL_HOST = ""
SSH_TUNNEL_PORT = 
SSH_TUNNEL_USER = ""
SSH_TUNNEL_PEM = r""
# The .pem identity file used to authenticate the SSH tunnel.

DB_TABLE = ""
# Table name where ML pipeline inserts detection events.

DB_CAMERA_ID = 
# The camera_id in the database that corresponds to your test stream.
# Only events with this camera_id will be checked.

# --- YOUR S3 BUCKET ---
S3_BUCKET = "your-s3-bucket-name"
# The bucket where ML pipeline stores event clips.
# The exact S3 key comes from the database (video_s3_key column).

# --- YOUR STREAMING SETUP (defaults match your .bat file) ---
PLAYLIST_PATH = "playlist.txt"
# Path to the playlist.txt file that ffmpeg reads.

HLS_OUTPUT_DIR = r""
# Where ffmpeg writes HLS files. Must match OUTPUT_DIR in your .bat.

HTTP_PORT = 
# Must match PORT in your .bat.

TUNNEL_NAME = ""
# Must match TUNNEL_NAME in your .bat.

STREAM_URL = ""
# Your public stream URL (without https://).
# The ML pipeline watches this.

TUNNEL_STARTUP_WAIT = 8.0
# Seconds to wait for Cloudflare Tunnel to establish connection.
# Increase to 15 if your network is slow.

# --- TIMING ---
WAIT_MULTIPLIER = 2.0
# Total wait = video_duration × this.
# For a 30s video with 2.0: waits 60s total.
# Increase to 3.0 or 4.0 if your ML pipeline is slow.

EXTRA_WAIT = 30.0
# After the main wait, keep polling S3 for this many more seconds.
# Increase to 60 if pipeline has variable latency.

POLL_INTERVAL = 10.0
# How often to check S3 (seconds). 10 is fine for most cases.

SETTLE_TIME = 5.0
# Seconds to wait after starting ffmpeg before stream is stable.

# --- OUTPUT ---
OUTPUT_EXCEL = "test_results.xlsx"
# Where to save the results spreadsheet.

# --- VIDEO MATCHER (advanced — defaults work fine) ---
MATCH_FPS = 1.0
# Frames per second to sample for matching. 1 is good.

MATCH_HASH_SIZE = 16
# pHash grid size. 16 is accurate. 8 is faster.

MATCH_HAMMING_THRESHOLD = 12
# Max hash distance for frame match. Increase if heavy transcoding.

MATCH_MIN_RATIO = 0.75
# Fraction of frames that must match. Decrease if getting false negatives.
