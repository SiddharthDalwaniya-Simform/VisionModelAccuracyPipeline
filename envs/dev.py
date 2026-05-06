# ============================================================
# DEV ENVIRONMENT CONFIG
# ============================================================
# Inherits shared defaults from base.py, overrides dev-specific values.

from envs.base import *  # noqa: F401,F403

# --- DATABASE (PostgreSQL via SSH Tunnel) ---
DB_HOST = "CHANGE_ME"
# RDS endpoint for dev. Example: "dev-db.xxxx.eu-central-1.rds.amazonaws.com"
DB_PORT = 0  # CHANGE_ME
DB_NAME = "CHANGE_ME"
DB_USER = "CHANGE_ME"
DB_PASSWORD = "CHANGE_ME"

# --- SSH TUNNEL ---
SSH_TUNNEL_HOST = "CHANGE_ME"
# IP or hostname of the dev bastion EC2 instance.
SSH_TUNNEL_PORT = 0  # CHANGE_ME
SSH_TUNNEL_USER = "CHANGE_ME"
SSH_TUNNEL_PEM = r"CHANGE_ME"
# Full path to your .pem key file. Example: r"C:\Users\you\Downloads\dev-key.pem"

DB_TABLE = "theft_event"
DB_CAMERA_ID = 0  # CHANGE_ME

# --- S3 + AWS ---
S3_BUCKET = "CHANGE_ME"
AWS_ACCESS_KEY_ID = "CHANGE_ME"
AWS_SECRET_ACCESS_KEY = "CHANGE_ME"
AWS_REGION = "CHANGE_ME"

# --- STREAMING ---
TUNNEL_NAME = "CHANGE_ME"
# Cloudflare Tunnel name. Example: "cctv-tunnel"
STREAM_URL = "CHANGE_ME"
# Public stream domain (without https://). Example: "cctv.yourdomain.store"
