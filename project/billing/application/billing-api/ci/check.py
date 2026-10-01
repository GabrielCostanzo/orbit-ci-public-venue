"""Sample check command for BuildBarrel's ordinary generated image workflow."""
import json
import os
import signal
import sys

from runtime import Cancelled, CleanupFailure, TutorialFailure, cancel, check, container, pull


def main():
    key = sys.argv[1] if len(sys.argv) == 2 else ""
    if key not in {"smoke", "integration"}:
        raise TutorialFailure("choose_smoke_or_integration")
    image = os.environ["BUILDBARREL_IMAGE_REFERENCE"]
    pull(image)
    with container(image, tenant=os.environ["BUILDBARREL_TENANT_ID"],
                   application=os.environ["BUILDBARREL_APPLICATION_ID"]) as name:
        passed = check(name, "smoke") and (key == "smoke" or check(name, "integration"))
    print(json.dumps({"kind": "buildbarrel_sample_check_receipt", "key": key,
                      "image_reference": image, "status": "passed" if passed else "failed",
                      "cleanup_status": "complete"}), flush=True)
    return 0 if passed else 1


if __name__ == "__main__":
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, cancel)
    try:
        sys.exit(main())
    except CleanupFailure as failure:
        print(json.dumps({"kind": "buildbarrel_sample_cleanup_failure", "container_name": failure.container_name,
                          "cleanup_status": "failed", "error": str(failure)}), flush=True)
        sys.exit(1)
    except Cancelled:
        sys.exit(130)
    except (TutorialFailure, KeyError, OSError):
        print("Sample check failed; inspect its Docker and cleanup log.", file=sys.stderr)
        sys.exit(1)
