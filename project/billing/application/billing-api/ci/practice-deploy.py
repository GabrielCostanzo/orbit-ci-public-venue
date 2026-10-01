"""Run only the exact guarded image, check its health, then remove its container."""
import json
import os
from pathlib import Path
import signal
import sys
import uuid

from runtime import Cancelled, CleanupFailure, TutorialFailure, cancel, check, container, image_reference


def main():
    image = image_reference(os.environ.get("BUILDBARREL_IMAGE_REFERENCE", ""))
    digest = os.environ.get("BUILDBARREL_IMAGE_DIGEST", "")
    assessment = str(uuid.UUID(os.environ.get("BUILDBARREL_ELIGIBILITY_ASSESSMENT_ID", "")))
    if image.rsplit("@", 1)[1] != digest:
        raise TutorialFailure("guard_image_mismatch")
    marker = Path(os.environ["BUILDBARREL_TUTORIAL_RECEIPT"]) if os.environ.get("BUILDBARREL_TUTORIAL_RECEIPT") else None
    def save():
        if marker:
            marker.write_text(json.dumps(receipt))
    receipt = {"execution_mode": "real", "image_reference": image, "digest": digest,
               "assessment_id": assessment, "command_executed": True, "command_exit_code": 1,
               "runtime_started": False, "cleanup_status": "not_run"}
    save()
    try:
        with container(image, tenant=os.environ["BUILDBARREL_TENANT_ID"],
                       application=os.environ["BUILDBARREL_APPLICATION_ID"]) as name:
            receipt.update(runtime_started=True, cleanup_status="pending")
            save()
            passed = check(name, "smoke")
    except CleanupFailure as failure:
        receipt.update(cleanup_status="failed", cleanup_error=str(failure), container_name=failure.container_name)
        save()
        print(json.dumps({"kind": "buildbarrel_tutorial_cleanup_failure", "error": str(failure),
                          "container_name": failure.container_name}), flush=True)
        raise
    except (Cancelled, TutorialFailure, OSError):
        # Reaching this handler means container.finally verified absence.
        receipt["cleanup_status"] = "complete"
        save()
        raise
    receipt["cleanup_status"] = "complete"
    receipt["command_exit_code"] = 0 if passed else 1
    save()
    print(json.dumps({"kind": "buildbarrel_sample_runtime_receipt", **receipt}), flush=True)
    print("Practice runtime checked /health and removed its exact owned container.", flush=True)
    return receipt["command_exit_code"]


if __name__ == "__main__":
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, cancel)
    try:
        sys.exit(main())
    except Cancelled:
        sys.exit(130)
    except (TutorialFailure, ValueError, KeyError, OSError):
        print("Practice runtime failed; inspect the CI job and cleanup status.", file=sys.stderr)
        sys.exit(1)
