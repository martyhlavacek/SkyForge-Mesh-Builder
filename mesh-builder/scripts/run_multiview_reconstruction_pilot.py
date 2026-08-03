from __future__ import annotations

import argparse
import getpass
import json
import sys
from pathlib import Path

import requests

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from app.macos_keychain import MacOSKeychain  # noqa: E402
from app.reconstruction_v1.bundle import (  # noqa: E402
    approve_bundle,
    build_bundle,
    render_contact_sheet,
    validate_bundle,
)
from app.reconstruction_v1.provider import (  # noqa: E402
    MeshyMultiImageProvider,
    SubmissionAuthorization,
)
from app.reconstruction_v1.state import TaskLog  # noqa: E402


class NetworkDisabledTransport:
    def request(self, method: str, url: str, **kwargs):
        raise RuntimeError(f"Network disabled in no-spend pilot: {method} {url}")


class RequestsTransport:
    def request(self, method, url, **kwargs):
        return requests.request(method, url, timeout=60, **kwargs)


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare the no-spend v0.8.1 multiview pilot")
    parser.add_argument("--bundle-root", required=True, type=Path)
    parser.add_argument("--asset-id", required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--top", required=True, type=Path)
    parser.add_argument("--front", required=True, type=Path)
    parser.add_argument("--right", required=True, type=Path)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--timestamp", required=True)
    parser.add_argument("--workflow-id", required=True)
    parser.add_argument("--submit-live", action="store_true", help="Explicit paid submission; never the default")
    parser.add_argument("--paid-provider-enabled", action="store_true")
    parser.add_argument("--maximum-credits", type=int)
    parser.add_argument("--confirm-bundle-digest")
    args = parser.parse_args()
    root = args.bundle_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    contact = root / "multiview_contact_sheet.png"
    bundle = build_bundle(root, asset_id=args.asset_id, profile_id=args.profile, source_commit=args.source_commit, created_at=args.timestamp, views=[("top", args.top), ("front", args.front), ("right", args.right)])
    render_contact_sheet(root, bundle, contact)
    bundle["contactSheet"] = {"path": contact.name, "sha256": __import__("hashlib").sha256(contact.read_bytes()).hexdigest()}
    bundle["bundleDigest"] = __import__("app.reconstruction_v1.bundle", fromlist=["content_digest"]).content_digest(bundle)
    bundle = approve_bundle(root, bundle, approved_at=args.timestamp, workflow_id=args.workflow_id)
    validate_bundle(root, bundle)
    provider = MeshyMultiImageProvider(
        RequestsTransport() if args.submit_live else NetworkDisabledTransport(),
        environ=None if args.submit_live else {"SKYFORGE_PROVIDER_NETWORK_DISABLED": "1"},
        submission_registry=(Path.home() / "Library" / "Application Support" / "SkyForge Mesh Builder" / "provider-submissions")
        if args.submit_live
        else None,
    )
    preview = provider.redact_for_evidence(provider.prepare_request(root, bundle))
    (root / "MultiviewAuthorityBundleV1.json").write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n")
    (root / "request_preview.json").write_text(json.dumps(preview, indent=2, sort_keys=True) + "\n")
    (root / "cost_estimate.json").write_text(json.dumps(provider.estimate_cost(), indent=2, sort_keys=True) + "\n")
    if not args.submit_live:
        print(json.dumps({"bundleDigest": bundle["bundleDigest"], "mode": "DRY_RUN", "paidOperationPerformed": False}, indent=2))
        return
    task_log = TaskLog(root / "provider_task_state.jsonl")
    if task_log.events():
        raise RuntimeError("A task lifecycle already exists for this output directory")
    for index, state in enumerate(("PREPARED", "BUNDLE_APPROVED", "COST_APPROVED", "SUBMITTING")):
        task_log.append(state, timestamp=f"{args.timestamp}+{index}")
    key = MacOSKeychain().read("com.skyforge.mesh-builder.meshy", getpass.getuser() or "skyforge-user")
    authorization_record = {
        "paidProviderEnabled": args.paid_provider_enabled,
        "approvedBundleDigest": bundle["bundleDigest"],
        "confirmedBundleDigest": args.confirm_bundle_digest,
        "estimatedCredits": provider.estimate_cost()["estimatedCredits"],
        "maximumCredits": args.maximum_credits,
        "apiKeyAvailable": bool(key),
        "providerSubmissionAttemptedAtRecordTime": False,
    }
    (root / "submission_authorization.json").write_text(
        json.dumps(authorization_record, indent=2, sort_keys=True) + "\n"
    )
    task_id = provider.submit_task(
        root,
        bundle,
        SubmissionAuthorization(
            paid_enabled=args.paid_provider_enabled,
            approved_bundle_digest=bundle["bundleDigest"],
            confirmed_bundle_digest=args.confirm_bundle_digest or "",
            maximum_credits=args.maximum_credits or 0,
            api_key=key,
        ),
    )
    task_log.append("SUBMITTED", timestamp=args.timestamp + "+submitted", details={"taskId": task_id})
    with (root / "raw_create_response.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(provider.last_create_response, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"bundleDigest": bundle["bundleDigest"], "mode": "LIVE_SUBMITTED", "taskId": task_id}, indent=2))


if __name__ == "__main__":
    main()
