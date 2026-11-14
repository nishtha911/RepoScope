"""Linux-only, single-instance Render experiment; not an always-on guarantee."""
import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time

from reposcope.staging_access import allowed_origins, credentials


def load_settings(environ):
    credentials(environ)
    allowed_origins(environ.get("STAGING_CORS_ORIGINS", ""))
    from sqlalchemy.engine import make_url
    try:
        url = make_url(environ.get("DATABASE_URL", ""))
        port = int(environ.get("PORT", "10000"))
    except Exception:
        raise ValueError("Invalid staging database URL or HTTP port") from None
    expected = environ.get("REPOSCOPE_EXPECTED_DB_HOST", "")
    if not expected or url.host != expected:
        raise ValueError("Database hostname does not match the explicitly expected staging host")
    if url.drivername != "postgresql+psycopg":
        raise ValueError("Staging DATABASE_URL must use postgresql+psycopg")
    if not 1 <= port <= 65535:
        raise ValueError("Invalid HTTP port")
    return port, expected


def memory_sample():
    for current, limit in (("/sys/fs/cgroup/memory.current", "/sys/fs/cgroup/memory.max"),
                           ("/sys/fs/cgroup/memory/memory.usage_in_bytes",
                            "/sys/fs/cgroup/memory/memory.limit_in_bytes")):
        try:
            used = int(Path(current).read_text().strip())
            maximum = Path(limit).read_text().strip()
            return {"event": "memory", "cgroup_bytes": used,
                    "cgroup_limit_bytes": int(maximum) if maximum.isdigit() else None}
        except (OSError, ValueError):
            continue
    return {"event": "memory", "cgroup_bytes": None, "cgroup_limit_bytes": None}


def stop_children(children, grace_seconds=20):
    # Each child is a new Linux session; signal its process group so Git and
    # other descendants are included. Hard stops rely on queue lease recovery.
    for child in children:
        try:
            os.killpg(child.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = time.monotonic() + grace_seconds
    while any(child.poll() is None for child in children) and time.monotonic() < deadline:
        time.sleep(0.1)
    for child in children:
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    for child in children:
        child.wait(timeout=5)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Validate settings only; never connect or claim jobs")
    args = parser.parse_args(argv)
    try:
        port, host = load_settings(os.environ)
        if shutil.which("git") is None:
            raise ValueError("Git executable was not found")
    except ValueError as exc:
        print(json.dumps({"event": "configuration_error", "message": str(exc)}), flush=True)
        return 2
    if args.check:
        print(json.dumps({"event": "configuration_valid", "database_connected": False,
                          "children_started": False}), flush=True)
        return 0
    if os.name != "posix":
        print(json.dumps({"event": "configuration_error", "message": "Combined launcher requires Linux"}), flush=True)
        return 2
    stopped = threading.Event()
    def request_stop(signum, frame):
        stopped.set()
    old_handlers = {sig: signal.signal(sig, request_stop) for sig in (signal.SIGTERM, signal.SIGINT)}
    children = []
    result = 1
    try:
        with tempfile.TemporaryDirectory(prefix="reposcope-staging-") as temporary:
            root = Path(temporary).resolve()
            workspace = root / "jobs"
            workspace.mkdir(mode=0o700)
            environment = os.environ.copy()
            environment.update({"PYTHONUNBUFFERED": "1", "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1",
                "OPENBLAS_NUM_THREADS": "1", "TOKENIZERS_PARALLELISM": "false",
                "HF_HOME": str(root / "hf-cache"), "HF_HUB_DISABLE_TELEMETRY": "1",
                "GIT_TERMINAL_PROMPT": "0", "PGCONNECT_TIMEOUT": "10"})
            api = [sys.executable, "-m", "uvicorn", "reposcope.staging_access:create_app", "--factory",
                   "--host", "0.0.0.0", "--port", str(port), "--workers", "1", "--timeout-graceful-shutdown", "15",
                   "--no-access-log"]
            worker = [sys.executable, "-m", "reposcope.jobs.worker", "--workspace", str(workspace),
                      "--expected-db-host", host, "--poll-seconds", "10", "--lease-seconds", "300",
                      "--clone-timeout-seconds", "60", "--max-job-seconds", "600"]
            worker_environment = environment.copy()
            for key in ("STAGING_USERNAME", "STAGING_PASSWORD"):
                worker_environment.pop(key, None)
            try:
                for name, command, env in (("api", api, environment), ("worker", worker, worker_environment)):
                    child = subprocess.Popen(command, env=env, stdin=subprocess.DEVNULL, start_new_session=True)
                    children.append(child)
                    print(json.dumps({"event": "child_started", "role": name, "pid": child.pid}), flush=True)
                next_sample = 0.0
                while not stopped.is_set():
                    exited = [(index, child.returncode) for index, child in enumerate(children) if child.poll() is not None]
                    if exited:
                        print(json.dumps({"event": "child_exited", "children": exited}), flush=True)
                        break
                    if time.monotonic() >= next_sample:
                        print(json.dumps(memory_sample()), flush=True)
                        next_sample = time.monotonic() + 30
                    stopped.wait(0.5)
                else:
                    result = 0
            finally:
                stop_children(children)
    finally:
        for sig, handler in old_handlers.items():
            signal.signal(sig, handler)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
