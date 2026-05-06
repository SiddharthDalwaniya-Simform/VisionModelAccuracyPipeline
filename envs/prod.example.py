# ============================================================
# PROD ENVIRONMENT CONFIG
# ============================================================
# Inherits shared defaults from base.py, overrides prod-specific values.
#
# HOW TO USE:
#   Copy this file to prod.py and fill in the values marked CHANGE_ME.
# ============================================================

from envs.base import *  # noqa: F401,F403

# --- DATABASE (PostgreSQL via SSH Tunnel) ---
DB_HOST = "CHANGE_ME"
# RDS endpoint for production. Example: "prod-db.xxxx.eu-central-1.rds.amazonaws.com"
DB_PORT = 0  # CHANGE_ME — PostgreSQL port
DB_NAME = "CHANGE_ME"
DB_USER = "CHANGE_ME"
DB_PASSWORD = "CHANGE_ME"

# --- SSH TUNNEL ---
SSH_TUNNEL_HOST = "CHANGE_ME"
# IP or hostname of the production bastion EC2 instance.
SSH_TUNNEL_PORT = 22
SSH_TUNNEL_USER = "CHANGE_ME"
# Example: "ec2-user" or "ubuntu" depending on the AMI
SSH_TUNNEL_PEM = r"CHANGE_ME"
# Full path to your .pem key file. Example: r"C:\Users\you\Downloads\prod-key.pem"

DB_TABLE = "theft_event"
DB_CAMERA_ID = 0  # CHANGE_ME — camera_id used for prod tests in the database

# --- S3 + AWS ---
S3_BUCKET = "CHANGE_ME"
# The S3 bucket where the production ML pipeline stores event clips.
AWS_ACCESS_KEY_ID = "CHANGE_ME"
AWS_SECRET_ACCESS_KEY = "CHANGE_ME"
AWS_REGION = "eu-central-1"

# --- STREAMING ---
TUNNEL_NAME = "CHANGE_ME"
# Cloudflare Tunnel name for production. Example: "cctv-tunnel-prod"
STREAM_URL = "CHANGE_ME"
# Public stream domain (without https://). Example: "cctv-prod.yourdomain.store"
