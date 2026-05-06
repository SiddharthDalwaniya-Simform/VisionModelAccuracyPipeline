"""
stream_manager.py — Controls the full streaming stack.

Manages three things:
  1. Python HTTP server  (serves HLS files from C:\\temp_stream_cloud)
  2. Cloudflare Tunnel   (exposes HTTP server to the internet)
  3. ffmpeg              (writes one video at a time as HLS)

HTTP server and tunnel start ONCE at the beginning and stay alive.
ffmpeg restarts per video.
"""

import logging
import os
import subprocess
import sys
import time
import threading
import urllib.request
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import config

log = logging.getLogger("stream")


class StreamManager:

    def __init__(self):
        self.ffmpeg_proc = None
        self.http_server = None
        self.http_thread = None
        self.tunnel_proc = None

    # =================================================================
    # HLS output directory
    # =================================================================

    def prepare_output_dir(self):
        """Clean old HLS segments. Create dir if needed."""
        d = config.HLS_OUTPUT_DIR
        if os.path.exists(d):
            self._clean_hls_files()
        else:
            os.makedirs(d)
        log.info("HLS output dir ready: %s", d)

    def _clean_hls_files(self):
        """Remove all .ts segments and .m3u8 playlist from the HLS output dir."""
        d = config.HLS_OUTPUT_DIR
        for f in Path(d).glob("*.ts"):
            f.unlink()
        m3u8 = Path(d) / "cctv.m3u8"
        if m3u8.exists():
            m3u8.unlink()

    def clean_between_videos(self):
        """Clean HLS segments between video runs so old data doesn't leak."""
        self._clean_hls_files()
        log.info("  HLS segments cleaned for next video.")

    # =================================================================
    # HTTP server
    # =================================================================

    def start_http_server(self):
        """Start a threaded HTTP server serving the HLS directory."""
        # Check if something is already running on the port
        if self._is_port_in_use(config.HTTP_PORT):
            log.info("HTTP server already running on port %d — skipping start.",
                     config.HTTP_PORT)
            return

        class _HLSHandler(SimpleHTTPRequestHandler):
            """Serves HLS files with correct MIME types and CORS headers."""

            extensions_map = {
                **SimpleHTTPRequestHandler.extensions_map,
                ".m3u8": "application/vnd.apple.mpegurl",
                ".ts": "video/mp2t",
            }

            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=config.HLS_OUTPUT_DIR, **kwargs)

            def end_headers(self):
                self.send_header("Access-Control-Allow-Origin", "*")
                if self.path.endswith(".m3u8"):
                    self.send_header("Cache-Control",
                                     "no-cache, no-store, must-revalidate")
                super().end_headers()

            def log_message(self, format, *args):
                pass  # suppress per-request noise

        self.http_server = ThreadingHTTPServer(("0.0.0.0", config.HTTP_PORT),
                                               _HLSHandler)
        self.http_thread = threading.Thread(target=self.http_server.serve_forever,
                                            daemon=True)
        self.http_thread.start()
        time.sleep(1)

        log.info("HTTP server started on port %d (threaded, serving %s)",
                 config.HTTP_PORT, config.HLS_OUTPUT_DIR)

    def _is_port_in_use(self, port: int) -> bool:
        """Check if a port is already in use."""
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(("127.0.0.1", port)) == 0

    def verify_http_server(self) -> bool:
        """Check that the HTTP server is responding."""
        try:
            url = f"http://127.0.0.1:{config.HTTP_PORT}/"
            urllib.request.urlopen(url, timeout=5)
            log.info("HTTP server verified: responding on port %d", config.HTTP_PORT)
            return True
        except Exception:
            log.error("HTTP server NOT responding on port %d", config.HTTP_PORT)
            return False

    # =================================================================
    # Cloudflare Tunnel
    # =================================================================

    def start_tunnel(self):
        """Start Cloudflare Tunnel."""
        # Check if cloudflared is installed
        try:
            subprocess.run(
                ["cloudflared", "version"],
                capture_output=True, check=True,
            )
        except FileNotFoundError:
            log.error("cloudflared not found! Install it first:")
            log.error("  https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/")
            raise RuntimeError("cloudflared not installed")

        self.tunnel_proc = subprocess.Popen(
            ["cloudflared", "tunnel", "run", config.TUNNEL_NAME],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        log.info("Starting Cloudflare Tunnel '%s'…", config.TUNNEL_NAME)

        # Wait for tunnel to establish connection
        time.sleep(config.TUNNEL_STARTUP_WAIT)

        if self.tunnel_proc.poll() is not None:
            # Process died — read stderr for the reason
            _, stderr = self.tunnel_proc.communicate(timeout=5)
            err_msg = stderr.decode(errors="replace").strip()[-500:]
            log.error("Cloudflare Tunnel failed to start!")
            log.error("  Error: %s", err_msg)
            raise RuntimeError(f"Tunnel failed: {err_msg}")

        log.info("Cloudflare Tunnel '%s' is running (PID %d)",
                 config.TUNNEL_NAME, self.tunnel_proc.pid)

    def verify_tunnel(self) -> bool:
        """Check that the tunnel process is still alive."""
        if self.tunnel_proc and self.tunnel_proc.poll() is None:
            log.info("Cloudflare Tunnel verified: process alive (PID %d)",
                     self.tunnel_proc.pid)
            return True
        # We didn't start it — check if it's running externally
        if self.tunnel_proc is None:
            log.info("Tunnel was started externally — assuming it's running.")
            return True
        log.error("Cloudflare Tunnel process has died!")
        return False

    # =================================================================
    # Playlist + ffmpeg
    # =================================================================

    def write_playlist(self, video_path: str):
        """Write a single video to playlist.txt."""
        with open(config.PLAYLIST_PATH, "w") as f:
            f.write(f"file '{video_path}'\n")
        log.info("  playlist.txt → %s", os.path.basename(video_path))

    def start_ffmpeg(self):
        """
        Start ffmpeg: reads playlist.txt → HLS output.

        Source videos are HEVC which VLC cannot play via HLS, so we
        transcode to H.264.  All other settings match the proven
        streaming command for smooth, gap-free playback.
        """
        hls_path = os.path.join(config.HLS_OUTPUT_DIR, config.HLS_PLAYLIST_NAME)

        cmd = [
            "ffmpeg",
            "-re",
            "-f", "concat",
            "-safe", "0",
            "-i", os.path.abspath(config.PLAYLIST_PATH),
            "-fflags", "+genpts",
            "-avoid_negative_ts", "make_zero",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-tune", "zerolatency",
            "-pix_fmt", "yuv420p",
            "-vf", "scale=-2:720",
            "-c:a", "aac",
            "-f", "hls",
            "-hls_time", "2",
            "-hls_list_size", "20",
            "-hls_flags", "delete_segments+omit_endlist",
            hls_path,
        ]

        log.debug("  ffmpeg cmd: %s", " ".join(cmd))

        # stderr goes to a temp file so we can read it on failure without
        # blocking ffmpeg (piped stderr fills up and stalls the process).
        self._ffmpeg_log = os.path.join(config.HLS_OUTPUT_DIR, "ffmpeg.log")
        self._ffmpeg_log_fh = open(self._ffmpeg_log, "w")
        self.ffmpeg_proc = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=self._ffmpeg_log_fh,
        )
        log.info("  ffmpeg started (PID %d) — transcoding HEVC→H.264 HLS…",
                 self.ffmpeg_proc.pid)
        time.sleep(config.SETTLE_TIME)

        # Fail fast — read stderr and raise if ffmpeg already died
        if self.ffmpeg_proc.poll() is not None:
            self._ffmpeg_log_fh.close()
            err_msg = Path(self._ffmpeg_log).read_text(errors="replace").strip()[-1500:]
            log.error("ffmpeg failed to start HLS stream.")
            log.error("ffmpeg stderr:\n%s", err_msg)
            raise RuntimeError("ffmpeg failed to generate HLS output")

        if not os.path.exists(hls_path) or os.path.getsize(hls_path) == 0:
            log.warning("  HLS playlist not yet populated after %.0fs — waiting for first segment…", config.SETTLE_TIME)
            # HEVC→H.264 transcode of the first 2-second segment from a
            # high-res source (2592×1944) can take 20-30s.  Wait patiently.
            for _ in range(60):
                time.sleep(1)
                if os.path.exists(hls_path) and os.path.getsize(hls_path) > 0:
                    break
                if self.ffmpeg_proc.poll() is not None:
                    break

            if not os.path.exists(hls_path) or os.path.getsize(hls_path) == 0:
                if self.ffmpeg_proc.poll() is not None:
                    self._ffmpeg_log_fh.close()
                    err_msg = Path(self._ffmpeg_log).read_text(errors="replace").strip()[-1500:]
                    log.error("ffmpeg exited before producing segments.")
                    log.error("ffmpeg stderr:\n%s", err_msg)
                    raise RuntimeError("ffmpeg failed to generate HLS output")
                else:
                    log.error("HLS playlist still empty after 60s — ffmpeg may be stuck.")
                    raise RuntimeError("HLS playlist not populated by ffmpeg")

        log.info("  HLS playlist ready: %s", hls_path)
        log.info("  Local stream:  http://127.0.0.1:%d/%s", config.HTTP_PORT, config.HLS_PLAYLIST_NAME)
        log.info("  Public stream: https://%s/%s", config.STREAM_URL, config.HLS_PLAYLIST_NAME)

        # Return the moment the stream became available — callers use this
        # as the anchor for DB polling so it's in sync with actual playback.
        stream_ready_time = datetime.utcnow()
        log.info("  Stream ready at %s UTC", stream_ready_time.strftime("%H:%M:%S"))
        return stream_ready_time

    def wait_for_stream_accessible(self, timeout: float = 60.0) -> datetime:
        """
        Wait until the first HLS segment is confirmed via the local HTTP
        server.  This is the "first frame visible" gate — DB polling must
        not start until this returns.

        Checks the local HTTP endpoint (fast, reliable) instead of the
        public Cloudflare tunnel URL which may be behind access policies.
        A non-blocking tunnel diagnostic check runs in the background.

        Returns the UTC datetime when the first segment was confirmed.
        """
        local_url = f"http://127.0.0.1:{config.HTTP_PORT}/{config.HLS_PLAYLIST_NAME}"
        log.info("  Waiting for first HLS segment (local): %s", local_url)

        start = time.time()
        last_err = None
        while time.time() - start < timeout:
            try:
                resp = urllib.request.urlopen(local_url, timeout=5)
                body = resp.read().decode(errors="replace")
                # #EXTINF means at least one .ts segment with video data
                if "#EXTINF" in body:
                    accessible_time = datetime.utcnow()
                    log.info("  ✓ First segment confirmed at %s UTC (took %.1fs)",
                             accessible_time.strftime("%H:%M:%S"),
                             time.time() - start)
                    # Background tunnel check (non-blocking, diagnostic only)
                    self._check_tunnel_async()
                    return accessible_time
                last_err = "Playlist has no segments yet"
            except Exception as exc:
                last_err = str(exc)
            time.sleep(1)

        log.warning("  First segment not confirmed after %.0fs: %s", timeout, last_err)
        log.warning("  Falling back to current time as stream start.")
        return datetime.utcnow()

    def _check_tunnel_async(self):
        """Non-blocking diagnostic check of the public tunnel URL."""
        def _check():
            url = f"https://{config.STREAM_URL}/{config.HLS_PLAYLIST_NAME}"
            try:
                resp = urllib.request.urlopen(url, timeout=10)
                body = resp.read().decode(errors="replace")
                if "#EXTINF" in body:
                    log.info("  Tunnel stream also accessible.")
                else:
                    log.warning("  Tunnel reachable but no HLS segments yet.")
            except Exception as exc:
                log.warning("  Tunnel diagnostic: %s (ML model may use different auth)", exc)
        threading.Thread(target=_check, daemon=True).start()

    def is_ffmpeg_running(self) -> bool:
        """True if ffmpeg is alive (video still playing)."""
        return self.ffmpeg_proc is not None and self.ffmpeg_proc.poll() is None

    def stop_ffmpeg(self):
        """Stop the current ffmpeg process."""
        if self.ffmpeg_proc and self.ffmpeg_proc.poll() is None:
            self.ffmpeg_proc.terminate()
            try:
                self.ffmpeg_proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.ffmpeg_proc.kill()
                self.ffmpeg_proc.wait()
            log.info("  ffmpeg stopped.")
        if hasattr(self, "_ffmpeg_log_fh") and self._ffmpeg_log_fh:
            self._ffmpeg_log_fh.close()
            self._ffmpeg_log_fh = None

    # =================================================================
    # Lifecycle
    # =================================================================

    def start_services(self):
        """Start HTTP server and Cloudflare Tunnel. Call once at the beginning."""
        log.info("")
        log.info("Starting services…")
        log.info("-" * 40)

        self.start_http_server()
        self.start_tunnel()

        # Verify both are healthy
        if not self.verify_http_server():
            raise RuntimeError("HTTP server is not healthy")
        if not self.verify_tunnel():
            raise RuntimeError("Cloudflare Tunnel is not healthy")

        log.info("-" * 40)
        log.info("All services running.")
        log.info("Local VLC URL:  http://127.0.0.1:%d/%s", config.HTTP_PORT, config.HLS_PLAYLIST_NAME)
        log.info("Public VLC URL: https://%s/%s", config.STREAM_URL, config.HLS_PLAYLIST_NAME)
        log.info("")

    def stop_all(self):
        """Stop everything: ffmpeg, HTTP server, tunnel."""
        self.stop_ffmpeg()
        if self.http_server:
            self.http_server.shutdown()
            log.info("HTTP server stopped.")
        if self.tunnel_proc and self.tunnel_proc.poll() is None:
            self.tunnel_proc.terminate()
            log.info("Cloudflare Tunnel stopped.")
        log.info("All services stopped.")
