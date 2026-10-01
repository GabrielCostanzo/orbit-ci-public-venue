"""Run before opening the publishing session; output stays in the real CI log."""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from urllib.parse import urlsplit


def origin(value: str) -> str:
    parsed = urlsplit(value)
    if (parsed.scheme not in {"https", "http"} or not parsed.hostname
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in {"", "/"}):
        raise argparse.ArgumentTypeError("Use a bare http(s) origin without credentials or a path.")
    return value.rstrip("/")


def run(command: list[str]) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(command, capture_output=True, text=True, timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--buildbarrel", required=True, type=origin)
    parser.add_argument("--harbor", required=True, type=origin)
    args = parser.parse_args()
    failures = 0

    def report(ok: bool, label: str, fix: str) -> None:
        nonlocal failures
        print(f"{'PASS' if ok else 'FAIL'} {label}" + ("" if ok else f": {fix}"), flush=True)
        failures += not ok

    report(sys.version_info >= (3, 10), "Python 3.10+", "Select a runner with Python 3.10 or newer.")
    present = {tool: shutil.which(tool) for tool in ("git", "curl", "jq", "docker")}
    for tool, path in present.items():
        report(bool(path), tool, f"Ask the runner operator to install {tool}, or select a prepared runner.")
    if present["docker"]:
        result = run(["docker", "info", "--format", "{{.ServerVersion}}"])
        report(result is not None and result.returncode == 0 and bool(result.stdout.strip()),
               "Docker daemon access", "Check the runner's isolated Docker endpoint and permissions. Do not use sudo or switch to a shared production engine.")
    if present["curl"]:
        for label, url, accepted in (
            ("BuildBarrel", args.buildbarrel + "/+version", {"200"}),
            ("Harbor", args.harbor + "/v2/", {"200", "401"}),
        ):
            result = run(["curl", "-q", "--silent", "--show-error", "--connect-timeout", "5",
                          "--max-time", "10", "--proto", "=http,https", "--output", "/dev/null",
                          "--write-out", "%{http_code}", url])
            code = result.stdout.strip() if result is not None else "timeout"
            ok = result is not None and result.returncode == 0 and code in accepted
            report(ok, f"{label} connectivity (HTTP {code})",
                   f"Check {url}, DNS, trusted TLS certificates and the runner's network route. Redirects and other HTTP responses are refused; Harbor 401 is an expected unauthenticated challenge.")
    print("Preflight failed; publishing session must not start." if failures else
          "Preflight passed. Authentication and publication are verified by the following real CI steps.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
