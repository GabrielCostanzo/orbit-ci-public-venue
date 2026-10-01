"""Bounded, exact-name Docker operations for the billing-api tutorial."""
from contextlib import contextmanager
import json
import os
import re
import signal
import subprocess
import time
import uuid


class TutorialFailure(Exception):
    """Only fixed, non-secret messages from this module reach terminal output."""


class CleanupFailure(TutorialFailure):
    def __init__(self, reason, container_name):
        super().__init__(reason)
        self.container_name = container_name


class Cancelled(Exception):
    pass


def cancel(_signum, _frame):
    raise Cancelled()


def child_environment():
    # Docker receives its private config and remote context, never BuildBarrel tokens.
    excluded = {"BUILDBARREL_VALIDATION_TOKEN", "BUILDBARREL_READ_KEY", "BUILDBARREL_PUBLISHER_KEY",
                "BUILDBARREL_SESSION", "GITHUB_TOKEN", "ACTIONS_ID_TOKEN_REQUEST_TOKEN"}
    return {key: value for key, value in os.environ.items() if key not in excluded}


def stop(process, *, timeout=5):
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=5)


def run(arguments, *, timeout=30, env=None, include_stderr=False, stop_timeout=5):
    process = subprocess.Popen(arguments, start_new_session=True, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, env=env or child_environment())
    try:
        stdout, stderr = process.communicate(timeout=timeout)
        return process.returncode, stdout + (stderr if include_stderr else "")
    except subprocess.TimeoutExpired:
        raise TutorialFailure("command_timeout") from None
    finally:
        stop(process, timeout=stop_timeout)


def image_reference(value):
    if not re.fullmatch(r"[a-zA-Z0-9._:/-]+@sha256:[0-9a-f]{64}", value):
        raise TutorialFailure("immutable_image_reference_required")
    return value


def pull(image):
    image_reference(image)
    if run(["docker", "pull", image], timeout=120)[0]:
        raise TutorialFailure("image_pull_failed")
    code, output = run(["docker", "image", "inspect", image, "--format", "{{json .RepoDigests}}"])
    try:
        digests = json.loads(output)
    except ValueError:
        digests = []
    if code or image not in (digests or []):
        raise TutorialFailure("pulled_image_digest_mismatch")


@contextmanager
def container(image, *, tenant, application):
    image_reference(image)
    tenant, application = str(uuid.UUID(tenant)), str(uuid.UUID(application))
    # The CI host's runtime names (its hooks set them and clean up by them) stay as they are.
    namespace = os.environ.get("ORBIT_CI_NS", "")
    build = os.environ.get("BUILDKITE_BUILD_NUMBER", "")
    if not re.fullmatch(r"orbitci-[0-9]+-j[0-9a-f]{12}", namespace):
        namespace = "buildbarrel-tutorial"
    name = namespace + "-" + uuid.uuid4().hex
    labels = {"buildbarrel.tutorial.tenant": tenant, "buildbarrel.tutorial.application": application,
              "buildbarrel.tutorial.container": name}
    if namespace != "buildbarrel-tutorial" and re.fullmatch(r"[0-9]+", build):
        labels["orbit.ci.build"] = build
    command = ["docker", "run", "--name", name, "--detach", "--network", "none", "--read-only",
               "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--pids-limit", "64",
               "--memory", "64m", "--cpus", "0.5"]
    for key, value in labels.items():
        command.extend(["--label", key + "=" + value])
    try:
        if run([*command, image], timeout=30)[0]:
            raise TutorialFailure("container_start_failed")
        yield name
    finally:
        # The name is assigned before launch, including a lost Docker response.
        # Removal is bounded and targets only this invocation's exact name.
        try:
            run(["docker", "rm", "--force", "--volumes", name], timeout=15)
            code, remaining = run(["docker", "ps", "--all", "--filter", "name=^/" + name + "$",
                                   "--format", "{{.Names}}"], timeout=10)
        except TutorialFailure:
            raise CleanupFailure("container_cleanup_timeout", name) from None
        except (Cancelled, OSError):
            raise CleanupFailure("container_cleanup_unavailable", name) from None
        if code or remaining.strip():
            raise CleanupFailure("container_cleanup_incomplete", name)


def check(name, key):
    if key not in {"smoke", "integration"}:
        raise TutorialFailure("unsupported_tutorial_check")
    path = "health" if key == "smoke" else "invoice"
    expected = {"application": "billing-api", "healthy": True} if key == "smoke" else {
        "subtotal": 100, "tax": 20, "total": 120}
    program = ("import json, urllib.request; "
               f"r=urllib.request.urlopen('http://127.0.0.1:8080/{path}', timeout=2); "
               f"assert r.status == 200 and json.load(r) == {expected!r}")
    deadline = time.monotonic() + 20
    while True:
        code, _ = run(["docker", "exec", name, "python", "-c", program], timeout=5)
        if code == 0:
            return True
        if key == "integration" or time.monotonic() >= deadline:
            return False
        time.sleep(0.5)
