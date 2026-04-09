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
import urllib.request
from pathlib import Path

import config

log = logging.getLogger("stream")


class StreamManager:

    def __init__(self):
        self.ffmpeg_proc = None
        self.http_proc = None
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
        """Start Python HTTP server serving the HLS directory."""
        # Check if something is already running on the port
        if self._is_port_in_use(config.HTTP_PORT):
            log.info("HTTP server already running on port %d — skipping start.",
                     config.HTTP_PORT)
            return

        self.http_proc = subprocess.Popen(
            [sys.executable, "-m", "http.server", str(config.HTTP_PORT)],
            cwd=config.HLS_OUTPUT_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        time.sleep(2)

        if self.http_proc.poll() is not None:
            log.error("HTTP server failed to start! Check if port %d is free.",
                      config.HTTP_PORT)
            raise RuntimeError(f"HTTP server failed on port {config.HTTP_PORT}")

        log.info("HTTP server started on port %d (PID %d)",
                 config.HTTP_PORT, self.http_proc.pid)

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
        Same command as your .bat, minus -stream_loop.
        """
        hls_path = os.path.join(config.HLS_OUTPUT_DIR, "cctv.m3u8")

        cmd = [
            "ffmpeg",
            "-re",
            "-f", "concat",
            "-safe", "0",
            "-i", config.PLAYLIST_PATH,
            "-fflags", "+genpts",
            "-avoid_negative_ts", "make_zero",
            "-c:v", "copy",
            "-c:a", "copy",
            "-f", "hls",
            "-hls_time", "2",
            "-hls_list_size", "20",
            "-hls_flags", "append_list+omit_endlist",
            hls_path,
        ]

        self.ffmpeg_proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        log.info("  ffmpeg started (PID %d)", self.ffmpeg_proc.pid)
        time.sleep(config.SETTLE_TIME)

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
        log.info("All services running. Stream URL: https://%s/", config.STREAM_URL)
        log.info("")

    def stop_all(self):
        """Stop everything: ffmpeg, HTTP server, tunnel."""
        self.stop_ffmpeg()
        if self.http_proc and self.http_proc.poll() is None:
            self.http_proc.terminate()
            log.info("HTTP server stopped.")
        if self.tunnel_proc and self.tunnel_proc.poll() is None:
            self.tunnel_proc.terminate()
            log.info("Cloudflare Tunnel stopped.")
        log.info("All services stopped.")
