# ============================================================
# STAGE ENVIRONMENT CONFIG
# ============================================================
# Inherits shared defaults from base.py, overrides stage-specific values.
# TODO: Update the values below with your staging environment credentials.

from envs.base import *  # noqa: F401,F403

# --- DATABASE (PostgreSQL via SSH Tunnel) ---
DB_HOST = "CHANGE_ME"
# RDS endpoint for staging. Example: "stage-db.xxxx.eu-central-1.rds.amazonaws.com"
DB_PORT = 0  # CHANGE_ME
DB_NAME = "CHANGE_ME"
DB_USER = "CHANGE_ME"
DB_PASSWORD = "CHANGE_ME"

# --- SSH TUNNEL ---
SSH_TUNNEL_HOST = "CHANGE_ME"
# IP or hostname of the staging bastion EC2 instance.
SSH_TUNNEL_PORT = 22
SSH_TUNNEL_USER = "ec2-user"
SSH_TUNNEL_PEM = r"CHANGE_ME"
# Full path to your .pem key file. Example: r"C:\Users\you\Downloads\stage-key.pem"

DB_TABLE = "theft_event"
DB_CAMERA_ID = 0  # CHANGE_ME

# --- S3 + AWS ---
S3_BUCKET = "CHANGE_ME"
AWS_ACCESS_KEY_ID = "CHANGE_ME"
AWS_SECRET_ACCESS_KEY = "CHANGE_ME"
AWS_REGION = "CHANGE_ME"

# --- STREAMING ---
TUNNEL_NAME = "CHANGE_ME"
# Cloudflare Tunnel name for staging. Example: "cctv-tunnel-stage"
STREAM_URL = "CHANGE_ME"
# Public stream domain (without https://). Example: "cctv-stage.yourdomain.store"
