import io
import json
import unittest
from unittest.mock import MagicMock, patch
import urllib.error

from bibleprep import tinker_access


class AccessTests(unittest.TestCase):
    def test_dry_run_does_not_read_credentials_or_network(self):
        with patch.object(tinker_access, "load_project_environment") as environment, \
             patch.object(tinker_access, "check_access") as network, \
             patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(tinker_access.main([]), 0)
        environment.assert_not_called()
        network.assert_not_called()

    def test_billing_error_never_discloses_provider_body(self):
        error = urllib.error.HTTPError("https://example.invalid", 402, "private account identifier", {}, io.BytesIO(b"PRIVATE-ACCOUNT-KEY"))
        with patch("urllib.request.build_opener") as opener:
            opener.return_value.open.side_effect = error
            result = tinker_access.check_access("PRIVATE-ACCOUNT-KEY")
        self.assertEqual(result["status"], "billing_required")
        self.assertNotIn("PRIVATE", json.dumps(result))
        self.assertEqual(result["model_calls"], 0)

    def test_catalog_exposes_only_expected_summary_fields(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({
            "supported_models": [{"model_name": "openai/gpt-oss-120b"}, {"model_name": "other/model"}],
            "account_private_field": "DO-NOT-EXPOSE",
        }).encode()
        with patch("urllib.request.build_opener") as opener:
            opener.return_value.open.return_value = response
            result = tinker_access.check_access("synthetic-key")
        self.assertEqual(result["status"], "ready")
        self.assertTrue(result["gpt_oss_120b_available"])
        self.assertFalse(result["gpt_oss_20b_available"])
        self.assertNotIn("DO-NOT-EXPOSE", json.dumps(result))

    def test_missing_key_never_sends_request(self):
        with patch("urllib.request.build_opener") as opener:
            self.assertEqual(tinker_access.check_access("")["status"], "missing_key")
        opener.assert_not_called()


if __name__ == "__main__":
    unittest.main()
