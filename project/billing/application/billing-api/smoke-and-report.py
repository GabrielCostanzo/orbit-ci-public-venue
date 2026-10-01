"""Run a real smoke check and report its outcome through the ordinary CLI."""
import argparse
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import uuid


class SmokeCancelled(Exception):
    pass


def _cancel(_signum, _frame):
    raise SmokeCancelled()


def _stop(process):
    # Signal the shell and its children together so smoke.sh removes the named
    # container on timeout/cancellation. A bounded second wait avoids hanging.
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()


def run_smoke(directory, image):
    process = None
    previous = {sig: signal.signal(sig, _cancel) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        process = subprocess.Popen(["sh", str(directory / "smoke.sh"), image], start_new_session=True)
        code = process.wait(timeout=240)
        if code in (130, 143, -signal.SIGINT, -signal.SIGTERM):
            return "cancelled"
        return "passed" if code == 0 else "failed"
    except (subprocess.TimeoutExpired, OSError):
        return "failed"
    except (KeyboardInterrupt, SmokeCancelled):
        return "cancelled"
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
        if process is not None:
            _stop(process)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant", type=uuid.UUID, required=True)
    parser.add_argument("--application", type=uuid.UUID, required=True)
    parser.add_argument("--build", type=uuid.UUID, required=True)
    parser.add_argument("--image", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[^\s@]+@sha256:[0-9a-f]{64}", args.image):
        parser.error("--image must name an immutable @sha256 digest")
    digest = args.image.rsplit("@", 1)[1]
    directory = Path(__file__).resolve().parent
    identity = ["--tenant", str(args.tenant), "--application", str(args.application),
                "--build", str(args.build), "--digest", digest]
    start = subprocess.run([
        "registry", "images", "validation", "start", *identity,
        "--key", "smoke", "--validation-plan", str(directory / "validation-plan.json"),
        "--provider", "laptop", "--run-id", "demo-" + uuid.uuid4().hex, "--json",
    ], check=True, capture_output=True, text=True)
    attempt = str(uuid.UUID(json.loads(start.stdout)["attempt_id"]))
    print(f"Started attempt {attempt}", flush=True)
    status = run_smoke(directory, args.image)
    # A report error stays an error. Never print a successful result if BuildBarrel
    # did not acknowledge it; the attempt ID above supports a manual retry.
    subprocess.run([
        "registry", "images", "validation", "report", *identity,
        "--attempt", attempt, "--status", status,
    ], check=True)
    return 0 if status == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
