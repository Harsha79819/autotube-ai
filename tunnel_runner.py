"""
AutoTube AI - Multi-Provider Static & Quick Tunnel Launcher (tunnel_runner.py)
Supports:
1. Option A: Ngrok Free Permanent Static Domain (NGROK_AUTHTOKEN, NGROK_STATIC_DOMAIN)
2. Option B: Cloudflare Zero Trust Named Tunnel (CLOUDFLARE_TUNNEL_TOKEN)
3. Fallback: Cloudflare Quick Tunnel (trycloudflare.com)
"""
import os
import re
import sys
import time
import signal
import atexit
import shutil
import argparse
import subprocess
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TUNNEL_URL_FILE = OUTPUT_DIR / "tunnel_url.txt"
TUNNEL_QR_FILE = OUTPUT_DIR / "tunnel_qr.png"

load_dotenv(ROOT / ".env")

# Search paths for cloudflared & ngrok
KNOWN_CLOUDFLARED_PATHS = [
    "/opt/homebrew/bin/cloudflared",
    "/usr/local/bin/cloudflared",
    "/usr/bin/cloudflared",
    Path.home() / ".local/bin/cloudflared",
    Path.home() / "bin/cloudflared",
    ROOT / "bin/cloudflared",
]

KNOWN_NGROK_PATHS = [
    "/opt/homebrew/bin/ngrok",
    "/usr/local/bin/ngrok",
    "/usr/bin/ngrok",
    Path.home() / ".local/bin/ngrok",
    Path.home() / "bin/ngrok",
    ROOT / "bin/ngrok",
]

def find_cloudflared_binary() -> str:
    """Locates the cloudflared executable on the system."""
    found = shutil.which("cloudflared")
    if found:
        return found
    for path in KNOWN_CLOUDFLARED_PATHS:
        p = Path(path)
        if p.exists() and os.access(p, os.X_OK):
            return str(p)
    return ""

def find_ngrok_binary() -> str:
    """Locates the ngrok executable on the system."""
    found = shutil.which("ngrok")
    if found:
        return found
    for path in KNOWN_NGROK_PATHS:
        p = Path(path)
        if p.exists() and os.access(p, os.X_OK):
            return str(p)
    return ""

def generate_qr_code(url: str):
    """
    Generates an ASCII QR code for terminal camera scanning
    and saves a high-res PNG to output/tunnel_qr.png for UI display.
    """
    try:
        import qrcode
        from PIL import Image

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=2,
        )
        qr.add_data(url)
        qr.make(fit=True)

        print("\n" + "─" * 50)
        print("📱 SCAN WITH PHONE CAMERA FOR INSTANT MOBILE ACCESS:")
        print("─" * 50)
        try:
            qr.print_ascii(invert=True)
        except Exception:
            try:
                qr.print_tty()
            except Exception:
                pass

        img = qr.make_image(fill_color="black", back_color="white")
        img.save(TUNNEL_QR_FILE)
        print(f"🖼️  QR Code saved to: {TUNNEL_QR_FILE}")

    except Exception as e:
        print(f"⚠️  QR code generation notice: {e}")

class BaseTunnelManager:
    def __init__(self, port: int = 8501, host: str = "localhost"):
        self.port = port
        self.host = host
        self.process = None
        self.public_url = None
        self._shutdown_called = False

    def _sig_handler(self, signum, frame):
        print("\nShutting down tunnel gracefully...")
        self.stop()
        sys.exit(0)

    def stop(self):
        if self._shutdown_called:
            return
        self._shutdown_called = True

        if TUNNEL_URL_FILE.exists():
            try:
                TUNNEL_URL_FILE.unlink()
            except Exception:
                pass

        if self.process and self.process.poll() is None:
            print("🛑 Terminating tunnel process...")
            try:
                self.process.terminate()
                self.process.wait(timeout=3)
            except Exception:
                self.process.kill()
            print("✅ Tunnel stopped.")

    def run_forever(self):
        if not self.process:
            return
        consecutive_errors = 0
        try:
            while self.process.poll() is None:
                line = self.process.stdout.readline() if self.process.stdout else None
                if line:
                    print(line, end="", flush=True)
                    if "Serve tunnel error" in line or "control stream encountered a failure" in line:
                        consecutive_errors += 1
                        if consecutive_errors >= 8:
                            print("\n⚠️ Detected persistent broken tunnel control stream (8 consecutive errors). Auto-restarting tunnel...")
                            self.stop()
                            sys.exit(1)
                    elif "Registered tunnel connection" in line or "HTTP" in line or "200" in line:
                        consecutive_errors = 0
                else:
                    time.sleep(0.5)
        except KeyboardInterrupt:
            self.stop()
            sys.exit(0)
        
        # If the process exited on its own, capture and forward exit code
        code = self.process.poll() if self.process else 1
        print(f"🛑 Tunnel process exited unexpectedly with code: {code}")
        self.stop()
        sys.exit(code if code is not None else 1)

class NgrokTunnelManager(BaseTunnelManager):
    """Manages Ngrok permanent static domain tunnel."""
    def __init__(self, port: int = 8501, host: str = "localhost", authtoken: str = None, domain: str = None):
        super().__init__(port, host)
        self.authtoken = authtoken or os.getenv("NGROK_AUTHTOKEN", "")
        self.domain = domain or os.getenv("NGROK_STATIC_DOMAIN", "")

    def start(self, timeout_sec: int = 25) -> str:
        binary = find_ngrok_binary()
        if not binary:
            print("\n" + "=" * 70)
            print("❌ ngrok binary not found on this system.")
            print("=" * 70)
            print("To use Ngrok static domains, install ngrok:")
            print("  🍏 macOS: brew install ngrok/ngrok/ngrok")
            print("  🐧 Linux: curl -s https://ngrok-agent.s3.amazonaws.com/ngrok.asc | sudo tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null && sudo apt update && sudo apt install ngrok")
            print("  🪟 Windows: winget install ngrok")
            print("=" * 70 + "\n")
            return ""

        if self.authtoken:
            try:
                subprocess.run([binary, "config", "add-authtoken", self.authtoken], check=True, stdout=subprocess.DEVNULL)
            except Exception as e:
                print(f"⚠️ Failed to configure ngrok authtoken: {e}")

        # Kill any stale ngrok processes before binding
        try:
            subprocess.run(["pkill", "-f", "ngrok http"], capture_output=True)
            time.sleep(0.5)
        except Exception:
            pass

        cmd = [binary, "http"]
        clean_domain = self.domain.replace("https://", "").replace("http://", "").strip().rstrip("/")
        if clean_domain:
            cmd.extend(["--url", clean_domain])
        cmd.append(str(self.port))
        cmd.extend(["--log", "stdout"])

        print("\n" + "=" * 70)
        print("🌐 STARTING NGROK PERMANENT STATIC TUNNEL")
        print("=" * 70)
        print(f"Target Port    : {self.port}")
        print(f"Static Domain  : {clean_domain or 'Dynamic'}")
        print("Launching ngrok tunnel...")

        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        atexit.register(self.stop)
        signal.signal(signal.SIGINT, self._sig_handler)
        signal.signal(signal.SIGTERM, self._sig_handler)

        # Verify the ngrok process didn't crash immediately upon launch
        time.sleep(1.5)
        if self.process.poll() is not None:
            err_output = self.process.stdout.read() if self.process.stdout else ""
            print(f"❌ ngrok failed to launch (exit code {self.process.poll()}): {err_output}")
            self.stop()
            return ""

        if clean_domain:
            self.public_url = f"https://{clean_domain}"
        else:
            time.sleep(1.5)
            # Fetch URL from local ngrok API
            try:
                import json
                import urllib.request
                req = urllib.request.Request("http://127.0.0.1:4040/api/tunnels")
                with urllib.request.urlopen(req, timeout=4) as resp:
                    data = json.loads(resp.read().decode())
                    for t in data.get("tunnels", []):
                        if t.get("public_url", "").startswith("https://"):
                            self.public_url = t["public_url"]
                            break
            except Exception:
                pass

        if not self.public_url:
            self.public_url = f"https://{clean_domain}" if clean_domain else ""

        if not self.public_url:
            print("⚠️ Could not establish ngrok tunnel.")
            self.stop()
            return ""

        # Validate endpoint reachability & check for ngrok monthly bandwidth exhaustion
        try:
            import urllib.request
            import urllib.error
            req = urllib.request.Request(self.public_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=4) as resp:
                pass
        except urllib.error.HTTPError as e:
            if e.code == 403:
                try:
                    err_body = e.read().decode(errors="ignore")
                except Exception:
                    err_body = ""
                if "ERR_NGROK_725" in err_body or "bandwidth limit" in err_body:
                    print("\n" + "!" * 70)
                    print("⚠️ NGROK BANDWIDTH LIMIT EXCEEDED FOR THE MONTH (ERR_NGROK_725)!")
                    print("This free ngrok account reached its monthly bandwidth limit.")
                    print("Switching over to Cloudflare Tunnel (unlimited bandwidth)...")
                    print("!" * 70 + "\n")
                    self.stop()
                    return ""
        except Exception:
            pass

        TUNNEL_URL_FILE.write_text(self.public_url, encoding="utf-8")

        print("\n" + "=" * 70)
        print("🎉 NGROK PERMANENT STATIC TUNNEL ONLINE!")
        print("=" * 70)
        print(f"🌍 Permanent URL : {self.public_url}")
        print(f"🔒 Local Service : http://localhost:{self.port}")
        print(f"🔑 Security PIN  : Protected by APP_PIN in auth_guard.py")
        print("=" * 70)

        generate_qr_code(self.public_url)
        return self.public_url

class CloudflareNamedTunnelManager(BaseTunnelManager):
    """Manages Cloudflare Zero Trust Named Tunnel using a configured token."""
    def __init__(self, port: int = 8501, host: str = "localhost", token: str = None, static_domain: str = None):
        super().__init__(port, host)
        self.token = token or os.getenv("CLOUDFLARE_TUNNEL_TOKEN", "")
        self.static_domain = static_domain or os.getenv("CLOUDFLARE_STATIC_DOMAIN", "")

    def start(self, timeout_sec: int = 25) -> str:
        binary = find_cloudflared_binary()
        if not binary:
            return ""

        cmd = [binary, "tunnel", "run", "--token", self.token]

        print("\n" + "=" * 70)
        print("🌐 STARTING CLOUDFLARE ZERO TRUST NAMED TUNNEL")
        print("=" * 70)
        print(f"Token Configured : {self.token[:8]}...{self.token[-4:] if len(self.token) > 12 else ''}")
        print(f"Static Domain    : {self.static_domain or 'Defined in Cloudflare Zero Trust dashboard'}")

        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        atexit.register(self.stop)
        signal.signal(signal.SIGINT, self._sig_handler)
        signal.signal(signal.SIGTERM, self._sig_handler)

        time.sleep(2)
        if self.process.poll() is not None:
            print("❌ cloudflared named tunnel process failed to start.")
            return ""

        clean_domain = self.static_domain.replace("https://", "").replace("http://", "").strip().rstrip("/")
        self.public_url = f"https://{clean_domain}" if clean_domain else "https://your-cloudflare-tunnel-domain"
        TUNNEL_URL_FILE.write_text(self.public_url, encoding="utf-8")

        print("\n" + "=" * 70)
        print("🎉 CLOUDFLARE NAMED TUNNEL RUNNING!")
        print("=" * 70)
        print(f"🌍 Permanent URL : {self.public_url}")
        print(f"🔒 Local Service : http://localhost:{self.port}")
        print("=" * 70)

        generate_qr_code(self.public_url)
        return self.public_url

class CloudflareQuickTunnelManager(BaseTunnelManager):
    """Manages free ephemeral Cloudflare Quick Tunnel (trycloudflare.com)."""
    def start(self, timeout_sec: int = 35) -> str:
        binary = find_cloudflared_binary()
        if not binary:
            return ""

        target_url = f"http://{self.host}:{self.port}"
        cmd = [binary, "tunnel", "--url", target_url]

        print("\n" + "=" * 70)
        print("🌐 STARTING CLOUDFLARE QUICK TUNNEL (FALLBACK)")
        print("=" * 70)
        print(f"Target Local URL : {target_url}")
        print("Establishing secure HTTPS tunnel via trycloudflare.com...")

        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        atexit.register(self.stop)
        signal.signal(signal.SIGINT, self._sig_handler)
        signal.signal(signal.SIGTERM, self._sig_handler)

        url_regex = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")
        start_time = time.time()
        while time.time() - start_time < timeout_sec:
            if self.process.poll() is not None:
                print(f"❌ cloudflared process terminated (exit code {self.process.returncode})")
                return ""

            line = self.process.stdout.readline()
            if not line:
                time.sleep(0.1)
                continue

            match = url_regex.search(line)
            if match:
                self.public_url = match.group(0)
                break

        if not self.public_url:
            print("⚠️ Could not detect quick tunnel URL within timeout.")
            self.stop()
            return ""

        TUNNEL_URL_FILE.write_text(self.public_url, encoding="utf-8")

        print("\n" + "=" * 70)
        print("🎉 CLOUDFLARE QUICK TUNNEL ONLINE!")
        print("=" * 70)
        print(f"🌍 Public HTTPS URL : {self.public_url}")
        print(f"🔒 Local Service    : {target_url}")
        print(f"🔑 Security PIN     : Protected by APP_PIN in auth_guard.py")
        print("=" * 70)

        generate_qr_code(self.public_url)
        return self.public_url

def resolve_tunnel_manager(mode: str = "auto", port: int = 8501, host: str = "localhost") -> BaseTunnelManager:
    """
    Selects the optimal tunnel manager based on configured .env variables:
    1. Ngrok static domain (if NGROK_STATIC_DOMAIN configured and ngrok installed)
    2. Cloudflare Named Tunnel (if CLOUDFLARE_TUNNEL_TOKEN configured and cloudflared installed)
    3. Cloudflare Quick Tunnel (default fallback)
    """
    ngrok_domain = os.getenv("NGROK_STATIC_DOMAIN", "").strip()
    ngrok_token = os.getenv("NGROK_AUTHTOKEN", "").strip()
    cf_token = os.getenv("CLOUDFLARE_TUNNEL_TOKEN", "").strip()
    cf_domain = os.getenv("CLOUDFLARE_STATIC_DOMAIN", "").strip()

    ngrok_bin = find_ngrok_binary()
    cf_bin = find_cloudflared_binary()

    if mode == "ngrok":
        return NgrokTunnelManager(port=port, host=host, authtoken=ngrok_token, domain=ngrok_domain)
    elif mode == "cloudflare-named":
        return CloudflareNamedTunnelManager(port=port, host=host, token=cf_token, static_domain=cf_domain)
    elif mode == "cloudflare-quick":
        return CloudflareQuickTunnelManager(port=port, host=host)

    # AUTO MODE RESOLUTION:
    if ngrok_domain and ngrok_token:
        if ngrok_bin:
            return NgrokTunnelManager(port=port, host=host, authtoken=ngrok_token, domain=ngrok_domain)
        else:
            print("⚠️ NGROK credentials configured, but 'ngrok' binary not found. Falling back to Cloudflare Quick Tunnel.")

    if cf_token and cf_bin:
        return CloudflareNamedTunnelManager(port=port, host=host, token=cf_token, static_domain=cf_domain)

    return CloudflareQuickTunnelManager(port=port, host=host)

def main():
    parser = argparse.ArgumentParser(description="AutoTube Remote Tunnel Runner (Ngrok Static / Cloudflare)")
    parser.add_argument("--port", type=int, default=8501, help="Local Streamlit port (default: 8501)")
    parser.add_argument("--host", type=str, default="localhost", help="Local host (default: localhost)")
    parser.add_argument("--mode", type=str, default="auto", choices=["auto", "ngrok", "cloudflare-named", "cloudflare-quick"], help="Tunnel mode")
    parser.add_argument("--start-app", action="store_true", help="Also start Streamlit app.py concurrently")
    args = parser.parse_args()

    app_process = None
    if args.start_app:
        print("🚀 Starting Streamlit application (app.py)...")
        app_cmd = [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(ROOT / "app.py"),
            "--server.port",
            str(args.port),
            "--server.headless",
            "true",
        ]
        app_process = subprocess.Popen(app_cmd)
        time.sleep(2.5)

    manager = resolve_tunnel_manager(mode=args.mode, port=args.port, host=args.host)
    url = manager.start()

    if not url and args.mode in ("auto", "ngrok"):
        print("🔄 Primary tunnel unavailable or quota exhausted. Falling back to Cloudflare Quick Tunnel...")
        manager = CloudflareQuickTunnelManager(port=args.port, host=args.host)
        url = manager.start()

    if url:
        print("\nTunnel is actively running. Press Ctrl+C anytime to stop.\n")
        try:
            manager.run_forever()
        finally:
            if app_process:
                app_process.terminate()
    else:
        print("❌ Tunnel failed to start. Exiting.")
        if app_process:
            app_process.terminate()
        sys.exit(1)

if __name__ == "__main__":
    main()

