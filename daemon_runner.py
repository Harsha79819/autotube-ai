"""
AutoTube AI - Background Daemon & Crash-Resistant Process Supervisor (daemon_runner.py)
Monitors Streamlit and Tunnel processes 24/7 with automatic crash recovery,
persistent rotating logging, and detached background execution.

Commands:
  python daemon_runner.py --start       # Start detached in background
  python daemon_runner.py --status      # Check health, PIDs, and public URL
  python daemon_runner.py --stop        # Gracefully stop all background processes
  python daemon_runner.py --foreground  # Run attached in terminal (for debugging)
"""
import os
import sys
import time
import json
import signal
import shutil
import argparse
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOGS_DIR = ROOT / "logs"
OUTPUT_DIR = ROOT / "output"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

PID_FILE = LOGS_DIR / "daemon.json"
SERVER_LOG = LOGS_DIR / "server.log"
TUNNEL_LOG = LOGS_DIR / "tunnel.log"
DAEMON_LOG = LOGS_DIR / "daemon.log"
TUNNEL_URL_FILE = OUTPUT_DIR / "tunnel_url.txt"
TUNNEL_QR_FILE = OUTPUT_DIR / "tunnel_qr.png"

MAX_LOG_BYTES = 10 * 1024 * 1024  # 10 MB per log file

def rotate_log_if_large(file_path: Path):
    """Rotates log file if it exceeds MAX_LOG_BYTES to prevent filling disk."""
    try:
        if file_path.exists() and file_path.stat().st_size > MAX_LOG_BYTES:
            backup = file_path.with_suffix(".log.1")
            if backup.exists():
                backup.unlink()
            file_path.rename(backup)
    except Exception:
        pass

def is_pid_alive(pid: int) -> bool:
    """Checks if a given process ID is actively running."""
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        # Process exists and is running, but current process lacks permission to signal it
        return True
    except ProcessLookupError:
        # Process does not exist
        return False
    except OSError as e:
        import errno
        return e.errno == errno.EPERM

def is_port_in_use(port: int) -> bool:
    """Checks if a TCP port is currently bound."""
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            return s.connect_ex(('127.0.0.1', port)) == 0
    except Exception:
        return False

def free_port_if_in_use(port: int):
    """Terminates any process occupying the given port to prevent 'port already in use' crash loops."""
    if not is_port_in_use(port):
        return
    try:
        res = subprocess.run(["lsof", "-ti", f":{port}"], capture_output=True, text=True)
        pids = [int(p.strip()) for p in res.stdout.strip().split() if p.strip().isdigit()]
        for p in pids:
            if p != os.getpid():
                try:
                    os.kill(p, signal.SIGTERM)
                except Exception:
                    pass
        time.sleep(0.5)
        for p in pids:
            if p != os.getpid():
                try:
                    os.kill(p, signal.SIGKILL)
                except Exception:
                    pass
    except Exception:
        pass


def read_daemon_state() -> dict:
    """Reads PID metadata from logs/daemon.json."""
    if not PID_FILE.exists():
        return {}
    try:
        return json.loads(PID_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}

def write_daemon_state(state: dict):
    """Saves PID metadata to logs/daemon.json."""
    try:
        PID_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"⚠️ Failed to write daemon state: {e}")

class ProcessSupervisor:
    """Supervises Streamlit and Tunnel child processes with automatic crash recovery."""

    def __init__(self, port: int = 8501, mode: str = "auto"):
        self.port = port
        self.mode = mode
        self.streamlit_proc = None
        self.tunnel_proc = None
        self.running = True
        self.started_at = datetime.now(timezone.utc).isoformat()

    def log_daemon(self, message: str):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{timestamp}] [SUPERVISOR] {message}\n"
        rotate_log_if_large(DAEMON_LOG)
        try:
            with open(DAEMON_LOG, "a", encoding="utf-8") as f:
                f.write(entry)
        except Exception:
            pass
        try:
            print(entry.strip(), flush=True)
        except Exception:
            pass

    def start_streamlit(self) -> subprocess.Popen:
        if is_port_in_use(self.port):
            self.log_daemon(f"Port {self.port} is already in use; clearing stale listener...")
            free_port_if_in_use(self.port)
            time.sleep(1.0)
        rotate_log_if_large(SERVER_LOG)
        server_out = open(SERVER_LOG, "a", encoding="utf-8")
        cmd = [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(ROOT / "app.py"),
            "--server.port",
            str(self.port),
            "--server.headless",
            "true",
        ]
        self.log_daemon(f"Spawning Streamlit server on port {self.port}...")
        proc = subprocess.Popen(
            cmd,
            cwd=str(ROOT),
            stdin=subprocess.DEVNULL,
            stdout=server_out,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        server_out.close()
        return proc

    def start_tunnel(self) -> subprocess.Popen:
        rotate_log_if_large(TUNNEL_LOG)
        tunnel_out = open(TUNNEL_LOG, "a", encoding="utf-8")
        cmd = [
            sys.executable,
            str(ROOT / "tunnel_runner.py"),
            "--port",
            str(self.port),
            "--mode",
            self.mode,
        ]
        self.log_daemon(f"Spawning Tunnel process (mode: {self.mode})...")
        proc = subprocess.Popen(
            cmd,
            cwd=str(ROOT),
            stdin=subprocess.DEVNULL,
            stdout=tunnel_out,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        tunnel_out.close()
        return proc

    def stop_all(self):
        self.running = False
        self.log_daemon("Shutting down supervisor and all child processes...")

        for name, proc in [("Tunnel", self.tunnel_proc), ("Streamlit", self.streamlit_proc)]:
            if proc and proc.poll() is None:
                self.log_daemon(f"Terminating {name} (PID: {proc.pid})...")
                try:
                    proc.terminate()
                    proc.wait(timeout=3)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass

        free_port_if_in_use(self.port)

        if PID_FILE.exists():
            try:
                PID_FILE.unlink()
            except Exception:
                pass
        self.log_daemon("Supervisor shutdown complete.")

    def run_loop(self):
        """Main supervisor monitoring loop with exponential backoff crash recovery."""
        signal.signal(signal.SIGINT, lambda s, f: self.stop_all())
        signal.signal(signal.SIGTERM, lambda s, f: self.stop_all())

        self.log_daemon("Supervisor loop starting...")
        self.streamlit_proc = self.start_streamlit()
        time.sleep(2.0)
        self.tunnel_proc = self.start_tunnel()

        state = {
            "daemon_pid": os.getpid(),
            "streamlit_pid": self.streamlit_proc.pid if self.streamlit_proc else None,
            "tunnel_pid": self.tunnel_proc.pid if self.tunnel_proc else None,
            "port": self.port,
            "started_at": self.started_at,
        }
        write_daemon_state(state)

        st_crashes = 0
        tunnel_crashes = 0
        last_st_restart = time.time()
        last_tunnel_restart = time.time()
        MAX_CONSECUTIVE_CRASHES = 5

        try:
            while self.running:
                time.sleep(2.0)

                # Reset backoff if processes have stayed healthy for over 45s
                if time.time() - last_st_restart > 45:
                    st_crashes = 0
                if time.time() - last_tunnel_restart > 45:
                    tunnel_crashes = 0

                # 1. Check Streamlit Health
                if self.streamlit_proc and self.streamlit_proc.poll() is not None:
                    code = self.streamlit_proc.poll()
                    st_crashes += 1
                    if st_crashes > MAX_CONSECUTIVE_CRASHES:
                        self.log_daemon(f"🛑 Streamlit crashed {st_crashes} consecutive times. Halting restart loop to prevent resource exhaustion. Check logs/server.log!")
                        self.streamlit_proc = None
                    else:
                        backoff = min(15, 2 ** min(st_crashes, 4))
                        self.log_daemon(f"⚠️ Streamlit exited unexpectedly (code {code})! Crash #{st_crashes}. Auto-restarting in {backoff}s...")
                        time.sleep(backoff)
                        self.streamlit_proc = self.start_streamlit()
                        last_st_restart = time.time()
                        state["streamlit_pid"] = self.streamlit_proc.pid
                        write_daemon_state(state)

                # 2. Check Tunnel Health
                if self.tunnel_proc and self.tunnel_proc.poll() is not None:
                    code = self.tunnel_proc.poll()
                    tunnel_crashes += 1
                    if tunnel_crashes > MAX_CONSECUTIVE_CRASHES:
                        self.log_daemon(f"🛑 Tunnel crashed {tunnel_crashes} consecutive times. Halting restart loop. Check logs/tunnel.log!")
                        self.tunnel_proc = None
                    else:
                        backoff = min(15, 2 ** min(tunnel_crashes, 4))
                        self.log_daemon(f"⚠️ Tunnel exited unexpectedly (code {code})! Crash #{tunnel_crashes}. Auto-restarting in {backoff}s...")
                        time.sleep(backoff)
                        self.tunnel_proc = self.start_tunnel()
                        last_tunnel_restart = time.time()
                        state["tunnel_pid"] = self.tunnel_proc.pid
                        write_daemon_state(state)


        except KeyboardInterrupt:
            self.stop_all()
        except Exception as exc:
            self.log_daemon(f"Supervisor unexpected exception: {exc}")
            self.stop_all()

# ============================================================
# CLI COMMAND HANDLERS
# ============================================================

def cmd_start(port: int = 8501, mode: str = "auto"):
    """Starts the supervisor in a detached background daemon session."""
    state = read_daemon_state()
    daemon_pid = state.get("daemon_pid")

    if daemon_pid and is_pid_alive(daemon_pid):
        print("\n" + "=" * 65)
        print(f"⚠️  AutoTube Daemon is already running! (PID: {daemon_pid})")
        print("=" * 65)
        cmd_status()
        return

    print("\n" + "=" * 65)
    print("🚀 LAUNCHING AUTOTUBE BACKGROUND PROCESS MANAGER")
    print("=" * 65)
    print(f"Local Port     : {port}")
    print(f"Tunnel Mode    : {mode}")
    print(f"Log Directory  : {LOGS_DIR}")
    print("Spawning detached supervisor process...")

    rotate_log_if_large(DAEMON_LOG)
    daemon_out = open(DAEMON_LOG, "a", encoding="utf-8")

    cmd = [
        sys.executable,
        str(ROOT / "daemon_runner.py"),
        "--run-supervisor",
        "--port",
        str(port),
        "--mode",
        mode,
    ]

    proc = subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        stdin=subprocess.DEVNULL,
        stdout=daemon_out,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    daemon_out.close()

    write_daemon_state({
        "daemon_pid": proc.pid,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "port": port,
    })

    print(f"Supervisor spawned with PID: {proc.pid}")
    print("Waiting for services and tunnel to initialize...")


    # Wait for tunnel URL to be written
    url = ""
    for _ in range(25):
        time.sleep(1.0)
        if TUNNEL_URL_FILE.exists():
            try:
                url = TUNNEL_URL_FILE.read_text(encoding="utf-8").strip()
                if url:
                    break
            except Exception:
                pass

    print("\n" + "=" * 65)
    print("🎉 AUTOTUBE 24/7 BACKGROUND DAEMON IS RUNNING!")
    print("=" * 65)
    print(f"🌍 Remote Mobile URL : {url or 'Establishing in background (check --status)'}")
    print(f"🔒 Local Streamlit   : http://localhost:{port}")
    print(f"📋 Supervisor PID    : {proc.pid}")
    print(f"📄 Server Log        : logs/server.log")
    print(f"📄 Tunnel Log        : logs/tunnel.log")
    print("=" * 65)
    print("Useful commands:")
    print("  python daemon_runner.py --status   # View live health & URL")
    print("  python daemon_runner.py --stop     # Stop all background services\n")

def cmd_status():
    """Checks and prints the current status of all background processes."""
    state = read_daemon_state()
    daemon_pid = state.get("daemon_pid")
    streamlit_pid = state.get("streamlit_pid")
    tunnel_pid = state.get("tunnel_pid")
    started_at = state.get("started_at", "N/A")
    port = state.get("port", 8501)

    daemon_alive = is_pid_alive(daemon_pid)
    st_alive = is_pid_alive(streamlit_pid)
    tunnel_alive = is_pid_alive(tunnel_pid)

    url = ""
    if TUNNEL_URL_FILE.exists():
        try:
            url = TUNNEL_URL_FILE.read_text(encoding="utf-8").strip()
        except Exception:
            pass

    print("\n" + "=" * 65)
    print("📊 AUTOTUBE SYSTEM STATUS & HEALTH")
    print("=" * 65)
    print(f"Status           : {'🟢 ACTIVE & RUNNING' if daemon_alive else '🔴 STOPPED'}")
    print(f"Supervisor (PID) : {daemon_pid or 'None'} ({'Alive' if daemon_alive else 'Dead'})")
    print(f"Streamlit (PID)  : {streamlit_pid or 'None'} ({'Alive' if st_alive else 'Dead'})")
    print(f"Tunnel (PID)     : {tunnel_pid or 'None'} ({'Alive' if tunnel_alive else 'Dead'})")
    print(f"Started At       : {started_at}")
    print(f"Local Server     : http://localhost:{port}")
    print(f"Remote HTTPS URL : {url or 'Not available'}")
    print(f"QR Code File     : {TUNNEL_QR_FILE if TUNNEL_QR_FILE.exists() else 'N/A'}")
    print(f"Server Log       : {SERVER_LOG}")
    print(f"Tunnel Log       : {TUNNEL_LOG}")
    print("=" * 65 + "\n")

def cmd_stop():
    """Stops all running background daemon processes."""
    state = read_daemon_state()
    daemon_pid = state.get("daemon_pid")
    streamlit_pid = state.get("streamlit_pid")
    tunnel_pid = state.get("tunnel_pid")

    print("\n" + "=" * 65)
    print("🛑 STOPPING AUTOTUBE BACKGROUND SERVICES")
    print("=" * 65)

    stopped_any = False
    for name, pid in [("Streamlit", streamlit_pid), ("Tunnel", tunnel_pid), ("Supervisor", daemon_pid)]:
        if pid and is_pid_alive(pid):
            print(f"Stopping {name} (PID: {pid})...")
            try:
                os.kill(pid, signal.SIGTERM)
                stopped_any = True
            except Exception as e:
                print(f"Notice stopping {name}: {e}")

    time.sleep(1.5)

    # Force kill if still lingering
    for name, pid in [("Streamlit", streamlit_pid), ("Tunnel", tunnel_pid), ("Supervisor", daemon_pid)]:
        if pid and is_pid_alive(pid):
            try:
                os.kill(pid, signal.SIGKILL)
            except Exception:
                pass

    if PID_FILE.exists():
        try:
            PID_FILE.unlink()
        except Exception:
            pass

    if TUNNEL_URL_FILE.exists():
        try:
            TUNNEL_URL_FILE.unlink()
        except Exception:
            pass

    port = state.get("port", 8501)
    free_port_if_in_use(port)

    try:
        subprocess.run(["pkill", "-f", "streamlit run.*app.py"], capture_output=True)
        subprocess.run(["pkill", "-f", "tunnel_runner.py"], capture_output=True)
    except Exception:
        pass

    if stopped_any or daemon_pid:
        print("✅ All AutoTube background processes have been cleanly terminated.\n")
    else:
        print("ℹ️  No active AutoTube processes were running.\n")


def main():
    parser = argparse.ArgumentParser(description="AutoTube Background Process Supervisor")
    parser.add_argument("--start", action="store_true", help="Start AutoTube in background detached mode")
    parser.add_argument("--status", action="store_true", help="Check status of background processes and public URL")
    parser.add_argument("--stop", action="store_true", help="Stop all background processes")
    parser.add_argument("--foreground", action="store_true", help="Run supervisor attached in terminal for debugging")
    parser.add_argument("--run-supervisor", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--port", type=int, default=8501, help="Streamlit port (default: 8501)")
    parser.add_argument("--mode", type=str, default="auto", choices=["auto", "ngrok", "cloudflare-named", "cloudflare-quick"], help="Tunnel mode")
    args = parser.parse_args()

    if args.start:
        cmd_start(port=args.port, mode=args.mode)
    elif args.status:
        cmd_status()
    elif args.stop:
        cmd_stop()
    elif args.foreground:
        print("Starting AutoTube supervisor in foreground mode (Ctrl+C to stop)...")
        supervisor = ProcessSupervisor(port=args.port, mode=args.mode)
        supervisor.run_loop()
    elif args.run_supervisor:
        supervisor = ProcessSupervisor(port=args.port, mode=args.mode)
        supervisor.run_loop()
    else:
        cmd_status()

if __name__ == "__main__":
    main()
