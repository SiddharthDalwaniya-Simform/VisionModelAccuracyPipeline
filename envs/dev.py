# ============================================================
# DEV ENVIRONMENT CONFIG
# ============================================================
# Inherits shared defaults from base.py, overrides dev-specific values.

from envs.base import *  # noqa: F401,F403

# --- DATABASE (PostgreSQL via SSH Tunnel) ---
DB_HOST = "changeMe"
DB_PORT = ChangeMe-Number
DB_NAME = "changeMe"
DB_USER = "changeMe"
DB_PASSWORD = "changeMe"

# --- SSH TUNNEL ---
SSH_TUNNEL_HOST = "changeMe"
SSH_TUNNEL_PORT = 22
SSH_TUNNEL_USER = "changeMe"
SSH_TUNNEL_PEM = r"changeMe"

DB_TABLE = "changeMe"
DB_CAMERA_ID = changeMe-Number

# --- S3 + AWS ---
S3_BUCKET = "changeMe"  # TODO: replace with actual dev bucket name
AWS_ACCESS_KEY_ID = "CHANGE_ME"
AWS_SECRET_ACCESS_KEY = "CHANGE_ME"
AWS_REGION = "changeMe"

# --- STREAMING ---
TUNNEL_NAME = "changeMe"
STREAM_URL = "changeMe"
