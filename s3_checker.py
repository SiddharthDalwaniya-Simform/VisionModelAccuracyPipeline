"""
s3_checker.py — Polls PostgreSQL (via SSH tunnel) for new ML events,
downloads clips from S3.

After a video is streamed, polls the theft_event table for new rows
matching our camera_id. Uses the video_s3_key from the DB to download
the clip directly from S3.
"""

import logging
import os
import time
from datetime import datetime

import boto3
import psycopg2
import psycopg2.extras
from sshtunnel import SSHTunnelForwarder

import config

log = logging.getLogger("s3")

S3_DOWNLOAD_RETRIES = 3
S3_RETRY_DELAY = 5  # seconds


class S3EventChecker:

    def __init__(self):
        self.s3 = self._make_s3_client()
        self.tunnel = None
        self.conn = None
        self._start_tunnel()
        self._connect_db()

    def _make_s3_client(self):
        """Build a boto3 S3 client using env-specific credentials if provided."""
        kwargs = {"region_name": config.AWS_REGION}
        if config.AWS_ACCESS_KEY_ID and config.AWS_ACCESS_KEY_ID != "CHANGE_ME":
            kwargs["aws_access_key_id"] = config.AWS_ACCESS_KEY_ID
            kwargs["aws_secret_access_key"] = config.AWS_SECRET_ACCESS_KEY
            log.debug("S3 client using explicit credentials for region %s", config.AWS_REGION)
        else:
            log.debug("S3 client using default credential chain (IAM role / ~/.aws/credentials)")
        return boto3.client("s3", **kwargs)

    def test_connections(self) -> bool:
        """
        Preflight check: verify SSH tunnel, DB, and S3 are all reachable.
        Logs a clear PASS/FAIL per service. Returns True only if all pass.
        """
        log.info("")
        log.info("─" * 50)
        log.info("  PREFLIGHT CONNECTION CHECK  [env=%s]", config.ENV)
        log.info("─" * 50)
        all_ok = True

        # ── SSH Tunnel ──────────────────────────────────────────
        if self.tunnel and self.tunnel.is_active:
            log.info("  [PASS] SSH tunnel  →  %s:%d",
                     config.SSH_TUNNEL_HOST, config.SSH_TUNNEL_PORT)
        else:
            log.error("  [FAIL] SSH tunnel  →  %s:%d  (not active)",
                      config.SSH_TUNNEL_HOST, config.SSH_TUNNEL_PORT)
            all_ok = False

        # ── PostgreSQL ───────────────────────────────────────────
        try:
            with self.conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM %s WHERE camera_id = %%s" % config.DB_TABLE,
                            (config.DB_CAMERA_ID,))
                count = cur.fetchone()[0]
            log.info("  [PASS] PostgreSQL  →  %s/%s  (camera_id=%d, existing rows=%d)",
                     config.DB_HOST, config.DB_NAME, config.DB_CAMERA_ID, count)
        except Exception as exc:
            log.error("  [FAIL] PostgreSQL  →  %s", exc)
            all_ok = False

        # ── S3 ───────────────────────────────────────────────────
        try:
            self.s3.head_bucket(Bucket=config.S3_BUCKET)
            log.info("  [PASS] S3 bucket   →  s3://%s", config.S3_BUCKET)
        except Exception as exc:
            log.error("  [FAIL] S3 bucket   →  s3://%s  (%s)", config.S3_BUCKET, exc)
            all_ok = False

        log.info("─" * 50)
        if all_ok:
            log.info("  All checks passed — ready to run.")
        else:
            log.error("  One or more checks FAILED — fix the issues above before running.")
        log.info("─" * 50)
        log.info("")
        return all_ok

    def _start_tunnel(self):
        """Open SSH tunnel to the database server."""
        if self.tunnel and self.tunnel.is_active:
            return
        self.tunnel = SSHTunnelForwarder(
            (config.SSH_TUNNEL_HOST, config.SSH_TUNNEL_PORT),
            ssh_username=config.SSH_TUNNEL_USER,
            ssh_pkey=config.SSH_TUNNEL_PEM,
            remote_bind_address=(config.DB_HOST, config.DB_PORT),
            set_keepalive=30,
        )
        self.tunnel.daemon_forward_servers = True
        self.tunnel.start()
        # Give the tunnel a moment to fully establish the forwarding channel
        time.sleep(2)
        log.info("SSH tunnel opened: localhost:%d → %s:%s via %s",
                 self.tunnel.local_bind_port,
                 config.DB_HOST, config.DB_PORT, config.SSH_TUNNEL_HOST)

    def _connect_db(self):
        """Establish (or re-establish) the PostgreSQL connection through the SSH tunnel."""
        if self.conn and not self.conn.closed:
            try:
                self.conn.close()
            except Exception:
                pass
        self.conn = psycopg2.connect(
            host="127.0.0.1",
            port=self.tunnel.local_bind_port,
            dbname=config.DB_NAME,
            user=config.DB_USER,
            password=config.DB_PASSWORD,
            sslmode="require",
        )
        self.conn.autocommit = True
        log.info("Connected to PostgreSQL via tunnel at 127.0.0.1:%d/%s",
                 self.tunnel.local_bind_port, config.DB_NAME)

    def _ensure_connection(self):
        """Check if DB connection is alive; reconnect if not."""
        try:
            with self.conn.cursor() as cur:
                cur.execute("SELECT 1")
        except (psycopg2.OperationalError, psycopg2.InterfaceError):
            log.warning("  DB connection lost — reconnecting…")
            if not self.tunnel.is_active:
                log.warning("  SSH tunnel also down — restarting…")
                self._start_tunnel()
            self._connect_db()

    def _query_events_after(self, after_time: datetime) -> list[dict]:
        """Query theft_event table for new events after the given time."""
        self._ensure_connection()
        query = f"""
            SELECT id, timestamp, theft_type, video_s3_key,
                   match_confidence, camera_id, detection_status,
                   created_at, thumbnail_s3_key
            FROM {config.DB_TABLE}
            WHERE camera_id = %s
              AND created_at > %s
              AND video_s3_key IS NOT NULL
            ORDER BY created_at ASC
        """
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, (config.DB_CAMERA_ID, after_time))
            rows = cur.fetchall()
        return [dict(r) for r in rows]

    def check_for_events(
        self,
        stream_start_time: datetime,
        timeout: float,
        stop_on_first_event: bool = True,
    ) -> list[dict]:
        """
        Poll the database for events created after stream_start_time.
        Polls every POLL_INTERVAL seconds for up to `timeout` seconds.
        Returns list of new events (dicts with video_s3_key etc.), or empty list.

        When stop_on_first_event is False, keeps polling for the full timeout
        and accumulates unique events so callers can inspect multiple detections
        during the same playback window.
        """
        start = time.time()
        seen_event_ids = set()
        collected_events = []

        while time.time() - start < timeout:
            events = self._query_events_after(stream_start_time)
            new_events = [e for e in events if e["id"] not in seen_event_ids]

            if new_events:
                log.info("  Found %d new event(s) in database.", len(new_events))
                for e in new_events:
                    seen_event_ids.add(e["id"])
                    collected_events.append(e)
                    log.info("    → %s (confidence=%s, theft_type=%s)",
                             e["video_s3_key"], e["match_confidence"], e["theft_type"])
                if stop_on_first_event:
                    return collected_events

            remaining = timeout - (time.time() - start)
            if remaining <= 0:
                break
            wait = min(config.POLL_INTERVAL, remaining)
            if collected_events:
                log.debug(
                    "  %d event(s) seen so far. Polling DB again in %.0fs (%.0fs left)…",
                    len(collected_events), wait, remaining,
                )
            else:
                log.debug("  No events yet. Polling DB in %.0fs (%.0fs left)…", wait, remaining)
            time.sleep(wait)

        if collected_events:
            log.info("  Polling window ended with %d event(s) found.", len(collected_events))
            return collected_events

        log.info("  Timeout — no events found in database for this video.")
        return []

    def download_clip(self, s3_key: str, local_dir: str) -> str:
        """Download an S3 clip to a local directory with retries. Returns local file path."""
        os.makedirs(local_dir, exist_ok=True)
        filename = os.path.basename(s3_key)
        local_path = os.path.join(local_dir, filename)

        for attempt in range(1, S3_DOWNLOAD_RETRIES + 1):
            try:
                self.s3.download_file(config.S3_BUCKET, s3_key, local_path)
                log.info("  Downloaded: %s", filename)
                return local_path
            except Exception as exc:
                if attempt < S3_DOWNLOAD_RETRIES:
                    log.warning("  S3 download failed (attempt %d/%d): %s — retrying in %ds…",
                                attempt, S3_DOWNLOAD_RETRIES, exc, S3_RETRY_DELAY)
                    time.sleep(S3_RETRY_DELAY)
                else:
                    log.error("  S3 download failed after %d attempts: %s", S3_DOWNLOAD_RETRIES, exc)
                    raise

    def close(self):
        """Close the database connection and SSH tunnel."""
        if self.conn and not self.conn.closed:
            self.conn.close()
            log.info("Database connection closed.")
        if self.tunnel and self.tunnel.is_active:
            self.tunnel.stop()
            log.info("SSH tunnel closed.")
