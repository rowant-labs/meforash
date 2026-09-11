"""Check Tinker account access without creating a session or generating tokens."""
from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request

from bibleprep.environment import load_project_environment

API_ROOT = "https://tinker.thinkingmachines.dev/services/tinker-prod"
BILLING_URL = "https://tinker.thinkingmachines.ai/billing/balance"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "Redirect refused", headers, fp)


def check_access(secret: str, timeout_seconds: int = 20) -> dict:
    """Return an allowlisted status. Never include provider error bodies or identities."""
    if not secret:
        return {"status": "missing_key", "model_calls": 0}
    if not 1 <= timeout_seconds <= 60:
        raise ValueError("Access timeout must be between 1 and 60 seconds")
    request = urllib.request.Request(
        API_ROOT + "/api/v1/get_server_capabilities",
        headers={"X-API-Key": secret, "User-Agent": "Tinker/Python 0.27.1", "Accept": "application/json"},
    )
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=timeout_seconds) as response:
            data = response.read(2_000_001)
        if len(data) > 2_000_000:
            return {"status": "unavailable", "reason": "response_size_limit", "model_calls": 0}
        parsed = json.loads(data)
        models = {m["model_name"] for m in parsed["supported_models"]}
        if not all(isinstance(name, str) for name in models):
            raise ValueError("Invalid model identifiers")
        return {
            "status": "ready", "available_model_count": len(models),
            "gpt_oss_120b_available": "openai/gpt-oss-120b" in models,
            "gpt_oss_20b_available": "openai/gpt-oss-20b" in models,
            "model_calls": 0,
        }
    except urllib.error.HTTPError as exc:
        if exc.code == 402:
            return {"status": "billing_required", "http_status": 402, "billing_url": BILLING_URL, "model_calls": 0}
        if exc.code in (401, 403):
            return {"status": "unauthorized", "http_status": exc.code, "model_calls": 0}
        return {"status": "unavailable", "http_status": exc.code, "model_calls": 0}
    except Exception:
        return {"status": "unavailable", "reason": "connection_or_response_error", "model_calls": 0}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Read the local key and check the account; never generate tokens.")
    args = parser.parse_args(argv)
    if not args.check:
        print(json.dumps({"status": "dry_run", "note": "Use --check for a read-only access check. Credentials were not read.", "model_calls": 0}, indent=2))
        return 0
    load_project_environment()
    result = check_access(os.environ.get("TINKER_API_KEY", ""))
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())
