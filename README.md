# Vision Model Accuracy Pipeline

An automated end-to-end testing framework that measures the accuracy of a shoplifting detection ML model. It streams offline test videos through a live HLS pipeline, monitors a PostgreSQL database for detection events, downloads generated clips from S3, optionally verifies them against source videos using perceptual hashing, and produces a color-coded Excel report.

---

## How It Works

```
┌─────────────────────────────────────────────────────────────────────┐
│  For each test video:                                               │
│                                                                     │
│  1. STREAM    → Write to playlist.txt → ffmpeg transcodes to HLS   │
│  2. EXPOSE    → Local HTTP server + Cloudflare Tunnel → public URL │
│  3. DETECT    → ML model consumes stream, writes events to DB      │
│  4. POLL      → Pipeline polls PostgreSQL for new theft_event rows  │
│  5. DOWNLOAD  → Fetch generated clip from S3                        │
│  6. VERIFY    → pHash comparison between clip and source (optional)│
│  7. REPORT    → Write result row to Excel (PASS / NO EVENT / etc.) │
└─────────────────────────────────────────────────────────────────────┘
```

### Services Lifecycle

| Service | Purpose | Lifecycle |
|---------|---------|-----------|
| HTTP Server (Python) | Serves HLS segments on `localhost:8080` | Starts once at beginning |
| Cloudflare Tunnel | Exposes local server to the internet | Starts once at beginning |
| ffmpeg | Transcodes HEVC → H.264 HLS per video | Restarts per video |
| SSH Tunnel | Routes PostgreSQL connection via bastion host | Persistent throughout run |

---

## Project Structure

```
run.py             ← Main entry point — orchestrates the entire test
config.py          ← Dynamic environment loader (reads --env flag)
stream_manager.py  ← Manages HTTP server, Cloudflare Tunnel, ffmpeg
s3_checker.py      ← SSH tunnel + PostgreSQL polling + S3 downloads
video_matcher.py   ← Perceptual hash (pHash) clip verification
excel_report.py    ← Generates color-coded test_results.xlsx
video_utils.py     ← Video duration (ffprobe) + file discovery helpers
test.py            ← Standalone DB connectivity check
envs/
  base.py          ← Shared default configuration
  dev.py           ← Development environment overrides
  stage.py         ← Staging environment overrides
  prod.py          ← Production environment overrides
```

---

## Setup

```bash
pip install -r requirements.txt
```

### Configure Environment Files

The `envs/` folder contains skeleton config files with `CHANGE_ME` placeholders. Fill in your actual values:

```
envs/base.py    ← video paths, HLS output dir, AWS region, timing
envs/dev.py     ← dev DB, SSH tunnel, S3 bucket, stream URL
envs/stage.py   ← stage DB, SSH tunnel, S3 bucket, stream URL
envs/prod.py    ← prod DB, SSH tunnel, S3 bucket, stream URL
```

After filling in your credentials, **protect them from accidental commits** by running once:

```bash
git update-index --skip-worktree envs/base.py envs/dev.py envs/stage.py envs/prod.py
```

This tells Git to ignore local changes to those files permanently. Your credentials will never be staged or pushed by accident.

To temporarily re-enable tracking (e.g. to push a legitimate skeleton update):

```bash
git update-index --no-skip-worktree envs/dev.py
# make changes, commit, push
git update-index --skip-worktree envs/dev.py
```

### Prerequisites

- **Python 3.8+**
- **ffmpeg** and **ffprobe** on PATH
- **Cloudflare Tunnel (`cloudflared`)** installed and configured
- **SSH key** (`.pem`) for bastion host access
- **AWS credentials** (via env vars, IAM role, or `~/.aws/credentials`)

---

## Usage

### Basic Run (Development)

```bash
python run.py
```

Runs the full pipeline against the **dev** environment by default.

### Target a Specific Environment

```bash
python run.py --env dev       # Development (default)
python run.py --env stage     # Staging
python run.py --env prod      # Production
```

Each environment has its own database, S3 bucket, camera ID, tunnel name, and stream URL.

### Dry Run

```bash
python run.py --dry-run
```

Discovers videos and runs preflight connection checks (SSH, DB, S3) **without** streaming any video. Useful for verifying configuration.

### Skip Services

```bash
python run.py --skip-services
```

Skips starting the HTTP server and Cloudflare Tunnel. Use this if they are already running manually.

### Logging Levels

```bash
python run.py --log debug     # Full verbose output (default)
python run.py --log normal    # Errors only in terminal
python run.py --log none      # Silent terminal; errors still go to log file
```

Log files are written to `logs/` with timestamped filenames.

### Combined Examples

```bash
python run.py --env stage --log debug
python run.py --env prod --skip-services --log normal
python run.py --dry-run --env stage
```

---

## Configuration

Configuration is managed via environment files in `envs/`. The `--env` flag (or `ENV` environment variable) selects which file to load. All files inherit from `envs/base.py`.

### Key Settings (in `envs/base.py`)

| Setting | Default | Description |
|---------|---------|-------------|
| `VIDEO_DIR` | `test_videos/` | Folder containing test videos |
| `HTTP_PORT` | `8080` | Local HTTP server port |
| `WAIT_MULTIPLIER` | `2.0` | Total poll time = video duration × this |
| `EXTRA_WAIT` | `30.0` | Additional seconds to poll after video ends |
| `POLL_INTERVAL` | `10.0` | Database polling frequency (seconds) |
| `ENABLE_VIDEO_MATCHING` | `False` | Enable pHash clip verification |
| `MATCH_FPS` | `1.0` | Frames per second sampled for hashing |
| `MATCH_HASH_SIZE` | `16` | pHash resolution (16×16 = 256-bit hash) |
| `MATCH_HAMMING_THRESHOLD` | `12` | Max bit distance for a frame match |
| `MATCH_MIN_RATIO` | `0.75` | Minimum % of frames that must match |
| `LOG_LEVEL` | `"debug"` | Logging verbosity |

### Per-Environment Overrides (dev / stage / prod)

Each environment file sets:
- `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`
- `DB_CAMERA_ID` — Filters events to a specific camera
- `S3_BUCKET` — Target S3 bucket for clips
- `SSH_TUNNEL_HOST`, `SSH_TUNNEL_PEM` — Bastion access
- `TUNNEL_NAME` — Cloudflare tunnel name
- `STREAM_URL` — Public stream domain

---

## What Happens During a Test

```
[1/50] shoplifting_001.mp4 (32.5s)
  playlist.txt → shoplifting_001.mp4
  ffmpeg started (PID 12345)
  Waiting for first HLS segment…
  Stream accessible — polling DB for events…
  Found event: theft_event id=482, s3_key=clips/ev_482.mp4
  Downloading clip from S3…
  ✔ MATCH (ratio=0.92)
  Excel row 2 → PASS
  ffmpeg stopped.

[2/50] normal_002.mp4 (28.0s)
  ...
  No events detected.
  Excel row 3 → NO EVENT
```

---

## Excel Report

The output file (`test_results.xlsx`) contains:

| Column | Content |
|--------|---------|
| Sr. No. | Sequential number |
| Offline Video Name | Source video filename |
| Duration (s) | Video length |
| Event Received? | YES / NO |
| S3 Link | S3 key of the detected clip |
| Match Result | MATCH / MISMATCH / SKIPPED |
| Match Ratio | Fraction of frames matched (0.0–1.0) |
| Status | PASS / NO EVENT / MISMATCH / CONN FAILED |
| Timestamp | When the test was run |
| Notes | Additional context |

**Color coding:** Green = PASS, Red = NO EVENT, Yellow = MISMATCH, Orange = Connection failure.

A summary section is appended at the bottom with total counts, detection rate (%), and execution time.

---

## Standalone Connection Test

```bash
python test.py
```

Verifies SSH tunnel → PostgreSQL connectivity without running the full pipeline. Useful for debugging infrastructure issues.

---

## Supported Video Formats

`.mp4`, `.mkv`, `.avi`, `.mov`, `.ts`, `.flv`, `.webm`

Videos are discovered recursively from `VIDEO_DIR` and sorted alphabetically.
