#!/usr/bin/env python3
"""
TERAWET Auto-Recovering Supervisor Daemon
Supervises web_dashboard.py and cloudflared tunnel.
Ensures zero-downtime, auto-restarts on crash, extracts public tunnel URL to tunnel_url.txt.
"""

import subprocess
import time
import re
import sys
import os
import signal
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PYTHON_BIN = sys.executable
CLOUDFLARED_BIN = BASE_DIR / "cloudflared"
TUNNEL_URL_FILE = BASE_DIR / "tunnel_url.txt"
LOG_FILE = BASE_DIR / "supervisor.log"

def log(msg: str):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[{timestamp}] {msg}"
    print(formatted, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(formatted + "\n")
    except Exception:
        pass

def start_dashboard():
    log("Starting web_dashboard.py...")
    proc = subprocess.Popen(
        [PYTHON_BIN, "web_dashboard.py"],
        cwd=str(BASE_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    return proc

def start_cloudflared():
    log("Starting cloudflared tunnel to http://localhost:8585...")
    proc = subprocess.Popen(
        [str(CLOUDFLARED_BIN), "tunnel", "--url", "http://localhost:8585"],
        cwd=str(BASE_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    return proc

def check_dashboard_health() -> bool:
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)
        res = s.connect_ex(('127.0.0.1', 8585))
        s.close()
        return res == 0
    except Exception:
        return False

def check_external_tunnel_health(url: str) -> bool:
    if not url or "trycloudflare.com" not in url:
        return True
    try:
        req = urllib.request.Request(f"{url}/api/leads", headers={"User-Agent": "SupervisorTunnelCheck/1.0"})
        with urllib.request.urlopen(req, timeout=7) as resp:
            return resp.status == 200
    except Exception as e:
        log(f"Public tunnel probe warning: {e}")
        return False

def main():
    log("=== TERAWET Supervisor Initialized ===")
    dash_proc = start_dashboard()
    time.sleep(2)

    cf_proc = start_cloudflared()
    current_url = ""

    def cleanup(signum, frame):
        log("Received termination signal. Stopping services...")
        try:
            if dash_proc and dash_proc.poll() is None:
                dash_proc.terminate()
            if cf_proc and cf_proc.poll() is None:
                cf_proc.terminate()
        except Exception:
            pass
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    last_health_check = time.time()
    last_tunnel_established = time.time()

    # Make cf_proc stdout non-blocking reading
    os.set_blocking(cf_proc.stdout.fileno(), False)
    os.set_blocking(dash_proc.stdout.fileno(), False)

    while True:
        try:
            # 1. Read cloudflared output for tunnel URL
            try:
                cf_output = cf_proc.stdout.read()
                if cf_output:
                    all_urls = re.findall(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", cf_output)
                    valid_urls = [u for u in all_urls if "api.trycloudflare.com" not in u]
                    if valid_urls:
                        new_url = valid_urls[0]
                        if new_url != current_url:
                            current_url = new_url
                            last_tunnel_established = time.time()
                            log(f"🌐 PUBLIC DASHBOARD URL: {current_url}")
                            log(f"🌐 BULGARIAN INTERFACE: {current_url}/?lang=bg")
                            with open(TUNNEL_URL_FILE, "w", encoding="utf-8") as f:
                                f.write(f"{current_url}\n")
            except Exception:
                pass

            # 2. Read dash output for logs
            try:
                dash_output = dash_proc.stdout.read()
                if dash_output:
                    for line in dash_output.strip().split("\n"):
                        if "TRIGGER" in line or "imported" in line or "error" in line.lower():
                            log(f"[Dashboard] {line}")
            except Exception:
                pass

            # 3. Check if processes died
            if dash_proc.poll() is not None:
                log(f"WARNING: web_dashboard.py exited (code {dash_proc.returncode}). Restarting in 2s...")
                time.sleep(2)
                dash_proc = start_dashboard()
                os.set_blocking(dash_proc.stdout.fileno(), False)

            if cf_proc.poll() is not None:
                log(f"WARNING: cloudflared exited (code {cf_proc.returncode}). Restarting in 3s...")
                time.sleep(3)
                cf_proc = start_cloudflared()
                os.set_blocking(cf_proc.stdout.fileno(), False)

            # 4. Periodic health check every 20 seconds
            now = time.time()
            if now - last_health_check > 20:
                last_health_check = now
                is_healthy = check_dashboard_health()
                if not is_healthy:
                    log("Local dashboard port 8585 unresponsive. Restarting web_dashboard.py...")
                    try:
                        dash_proc.terminate()
                        dash_proc.wait(timeout=3)
                    except Exception:
                        dash_proc.kill()
                    time.sleep(1)
                    dash_proc = start_dashboard()
                    os.set_blocking(dash_proc.stdout.fileno(), False)

                # Check external tunnel health if tunnel has been established for > 15 seconds
                if current_url and (now - last_tunnel_established > 15):
                    tunnel_ok = check_external_tunnel_health(current_url)
                    if not tunnel_ok:
                        log(f"Public tunnel {current_url} dropped or revoked! Rebuilding tunnel...")
                        try:
                            cf_proc.terminate()
                            cf_proc.wait(timeout=3)
                        except Exception:
                            cf_proc.kill()
                        current_url = ""
                        time.sleep(1)
                        cf_proc = start_cloudflared()
                        os.set_blocking(cf_proc.stdout.fileno(), False)

            time.sleep(1)
        except Exception as e:
            log(f"Supervisor loop exception: {e}")
            time.sleep(2)

if __name__ == "__main__":
    main()
