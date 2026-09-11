import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.request

from bibleprep import fetch_comparison as fetch


class FetchComparisonTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.manifest_path = self.root / "comparison.json"
        self.destination = self.root / "tokenizers"
        self.data = b'{"fixture": "public tokenizer"}'
        self.entry = {"path": "tokenizer.json", "bytes": len(self.data),
                      "sha256": hashlib.sha256(self.data).hexdigest(),
                      "url": f"https://huggingface.co/example/model/resolve/{'a' * 40}/tokenizer.json"}
        self.model = {"id": "example/model", "slug": "example-model", "revision": "a" * 40,
                      "tokenizer_repository": "example/model", "files": [self.entry]}
        self.manifest = {"schema_version": 1, "models": [self.model]}

    def write_manifest(self):
        self.manifest_path.write_text(json.dumps(self.manifest), encoding="utf-8")

    def run_fetch(self, selected=None):
        self.write_manifest()
        return fetch.fetch_assets(self.manifest_path, self.destination, selected)

    def test_download_is_verified_and_reused_without_network(self):
        with patch.object(fetch, "_download", return_value=self.data) as download:
            first = self.run_fetch()
            second = self.run_fetch()
        download.assert_called_once_with(self.entry)
        self.assertEqual(first[0]["status"], "downloaded")
        self.assertEqual(second[0]["status"], "verified")
        self.assertEqual((self.destination / self.model["slug"] / "tokenizer.json").read_bytes(), self.data)
        self.assertEqual(list(self.destination.rglob(".tokenizer-*")), [])

    def test_invalid_manifest_fields_fail_before_download_or_destination_creation(self):
        cases = [
            ("revision", "main"), ("slug", "../escape"), ("slug", "/absolute"),
            ("tokenizer_repository", "../model"),
            ("path", "model.safetensors"), ("path", "../tokenizer.json"),
            ("path", "/tokenizer.json"), ("path", "subdir/tokenizer.json"),
            ("path", "tokenization_other.py"), ("path", "modeling_kimi.py"),
            ("sha256", "not-a-hash"), ("bytes", True), ("bytes", 0),
            ("bytes", fetch.MAX_ASSET_BYTES + 1),
            ("url", self.entry["url"].replace("huggingface.co", "example.invalid")),
            ("url", self.entry["url"].replace("example/model", "other/model")),
            ("url", self.entry["url"].replace("a" * 40, "b" * 40)),
            ("url", self.entry["url"] + "?download=true"),
        ]
        original = copy.deepcopy(self.manifest)
        for key, value in cases:
            with self.subTest(key=key, value=value):
                self.manifest = copy.deepcopy(original)
                target = self.manifest["models"][0]
                if key in {"path", "sha256", "bytes", "url"}:
                    target = target["files"][0]
                target[key] = value
                with patch.object(fetch, "_download") as download, self.assertRaises(ValueError):
                    self.run_fetch()
                download.assert_not_called()
                self.assertFalse(self.destination.exists())

    def test_all_models_validated_before_fetching_first_asset(self):
        invalid = copy.deepcopy(self.model)
        invalid["slug"] = "second-model"
        invalid["id"] = "example/second"
        invalid["files"][0]["path"] = "weights.bin"
        self.manifest["models"].append(invalid)
        with patch.object(fetch, "_download") as download, self.assertRaises(ValueError):
            self.run_fetch()
        download.assert_not_called()

    def test_bad_download_never_publishes_file(self):
        for data in (self.data[:-1], b"!" * len(self.data), self.data + b"!"):
            with self.subTest(data=data), patch.object(fetch, "_download", return_value=data), self.assertRaises(ValueError):
                self.run_fetch()
            self.assertFalse((self.destination / self.model["slug"] / "tokenizer.json").exists())

    def test_invalid_existing_file_is_preserved_without_network(self):
        folder = self.destination / self.model["slug"]
        folder.mkdir(parents=True)
        path = folder / "tokenizer.json"
        path.write_bytes(b"changed locally")
        with patch.object(fetch, "_download") as download, self.assertRaises(ValueError):
            self.run_fetch()
        download.assert_not_called()
        self.assertEqual(path.read_bytes(), b"changed locally")

    def test_symlink_asset_is_not_read_or_replaced(self):
        folder = self.destination / self.model["slug"]
        folder.mkdir(parents=True)
        outside = self.root / "outside.json"
        outside.write_bytes(self.data)
        path = folder / "tokenizer.json"
        path.symlink_to(outside)
        with patch.object(fetch, "_download") as download, self.assertRaises(ValueError):
            self.run_fetch()
        download.assert_not_called()
        self.assertTrue(path.is_symlink())

    def test_unknown_selection_fails_without_network(self):
        with patch.object(fetch, "_download") as download, self.assertRaises(ValueError):
            self.run_fetch(["missing-model"])
        download.assert_not_called()
        self.assertFalse(self.destination.exists())

    def test_allowlisted_nested_tiktoken_asset_and_symlink_protection(self):
        self.entry["path"] = "tiktoken/tokenizer.model"
        self.entry["url"] = self.entry["url"].replace("tokenizer.json", self.entry["path"])
        with patch.object(fetch, "_download", return_value=self.data):
            result = self.run_fetch()
        self.assertEqual(result[0]["path"], "tiktoken/tokenizer.model")
        folder = self.destination / self.model["slug"] / "tiktoken"
        (folder / "tokenizer.model").unlink()
        folder.rmdir()
        outside = self.root / "outside"
        outside.mkdir()
        folder.symlink_to(outside, target_is_directory=True)
        with patch.object(fetch, "_download") as download, self.assertRaises(ValueError):
            self.run_fetch()
        download.assert_not_called()
        self.assertEqual(list(outside.iterdir()), [])

    def test_selection_and_extra_metadata_do_not_download_unselected_model(self):
        extra = copy.deepcopy(self.model)
        extra.update({"slug": "second-model", "id": "example/second"})
        self.manifest["models"].append(extra)
        self.manifest["support_files"] = [{"url": "https://example.invalid/private.py"}]
        with patch.object(fetch, "_download", return_value=self.data) as download:
            result = self.run_fetch(["second-model"])
        download.assert_called_once()
        self.assertEqual([row["model"] for row in result], ["second-model"])
        self.assertFalse((self.destination / "example-model").exists())

    def test_kimi_source_assets_are_checked_and_downloaded_without_execution(self):
        payload = b"raise RuntimeError('Downloaded tokenizer code must not execute during fetch')\n"
        for name in ("tiktoken.model", "tokenization_kimi.py", "tool_declaration_ts.py"):
            with self.subTest(name=name):
                self.entry.update({
                    "path": name, "bytes": len(payload),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "url": f"https://huggingface.co/example/model/resolve/{'a' * 40}/{name}",
                })
                with patch.object(fetch, "_download", return_value=payload) as download:
                    result = self.run_fetch()
                download.assert_called_once_with(self.entry)
                self.assertEqual(result[0]["status"], "downloaded")
                self.assertEqual((self.destination / self.model["slug"] / name).read_bytes(), payload)

    def test_cli_uses_explicit_manifest_without_mutating_default(self):
        with patch.object(fetch, "fetch_assets", return_value=[]) as fetch_assets, \
             patch("builtins.print"):
            self.assertEqual(fetch.main(["--manifest", str(self.manifest_path),
                                         "--model", "kimi-k2.6"]), 0)
        fetch_assets.assert_called_once_with(self.manifest_path,
                                             fetch.ROOT / "data/raw/tokenizers", ["kimi-k2.6"])

    def test_download_read_bound_and_public_headers(self):
        response = io.BytesIO(self.data)
        response.geturl = lambda: self.entry["url"]
        with patch("urllib.request.build_opener") as opener:
            opener.return_value.open.return_value = response
            self.assertEqual(fetch._download(self.entry), self.data)
        request = opener.return_value.open.call_args.args[0]
        self.assertNotIn("authorization", {key.lower() for key, _ in request.header_items()})
        self.assertNotIn("x-api-key", {key.lower() for key, _ in request.header_items()})
        response = io.BytesIO(self.data + b"too much")
        response.geturl = lambda: self.entry["url"]
        with patch("urllib.request.build_opener") as opener:
            opener.return_value.open.return_value = response
            with self.assertRaisesRegex(ValueError, "byte count"):
                fetch._download(self.entry)

    def test_redirect_rejects_nonpublic_origins_and_accepts_hf_storage(self):
        handler = fetch.PublicAssetRedirect()
        request = urllib.request.Request(self.entry["url"])
        for target in ("http://huggingface.co/file", "https://evil.example/file",
                       "https://huggingface.co.evil.example/file", "https://user:pass@huggingface.co/file"):
            with self.subTest(target=target), self.assertRaises(ValueError):
                handler.redirect_request(request, None, 302, "redirect", {}, target)
        target = "https://cas-bridge.xethub.hf.co/public-asset?signature=fixture"
        redirect = handler.redirect_request(request, None, 302, "redirect", {}, target)
        self.assertEqual(redirect.full_url, target)

    def test_failed_atomic_replace_cleans_temporary_file(self):
        with patch.object(fetch, "_download", return_value=self.data), \
             patch.object(fetch.os, "replace", side_effect=OSError("fixture failure")), \
             self.assertRaises(OSError):
            self.run_fetch()
        self.assertEqual(list(self.destination.rglob(".tokenizer-*")), [])
        self.assertFalse((self.destination / self.model["slug"] / "tokenizer.json").exists())


if __name__ == "__main__":
    unittest.main()
