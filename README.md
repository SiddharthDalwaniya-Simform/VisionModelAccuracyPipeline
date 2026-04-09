# Shoplifting Detection Test Orchestrator

## Files

```
config.py          ← EDIT THIS FIRST (the only file you change)
run.py             ← RUN THIS (starts everything, runs the test)
stream_manager.py  ← Starts HTTP server, Cloudflare Tunnel, ffmpeg
s3_checker.py      ← Polls S3 for event clips
video_matcher.py   ← pHash clip verification
excel_report.py    ← Writes color-coded test_results.xlsx
video_utils.py     ← Video duration + file discovery helpers
requirements.txt   ← Python dependencies
```

## Setup (one time)

```bash
pip install -r requirements.txt
```

## Usage

### 1. Edit config.py — change these 3 lines

```python
VIDEO_DIR  = r"C:\your\100\test\videos"
S3_BUCKET  = "your-s3-bucket-name"
S3_PREFIX  = "events/"
```

### 2. Run

```bash
python run.py
```

This will:
  1. Start HTTP server on port 8080
  2. Start Cloudflare Tunnel (cctv-tunnel)
  3. Verify both are healthy
  4. For each video: stream → wait → check S3 → verify → update Excel
  5. Stop everything when done

### Other modes

```bash
python run.py --dry-run         # Create Excel skeleton without streaming
python run.py --skip-services   # If HTTP server + tunnel already running
```

## What happens during the test

```
[1/100] shoplifting_001.mp4 (32.5s)
  playlist.txt → shoplifting_001.mp4
  ffmpeg started (PID 12345)
  Waiting 33s for video to play…
  Waiting 33s more for ML pipeline…
  Checking S3 (polling up to 30s)…
  Found 1 event clip(s) in S3.
  Event found: s3://bucket/events/clip_abc.mp4
  ✔ MATCH (ratio=0.92)
  Excel row 2 → PASS
  ffmpeg stopped.
```

Excel updates live — open it while the test runs.
