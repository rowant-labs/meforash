import hashlib
from contextlib import closing
import http.client
import json
from pathlib import Path
import socket
import tempfile
import threading
import unittest
from unittest.mock import patch

from bibleprep import railway_deployment as subject


class RuntimeBundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        for index, (_, relative) in enumerate(subject.BUNDLE_FILES):
            path = self.source / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(f"fixture-{index}-{relative}".encode())

    def export(self):
        output = self.root / "private-bundle"
        with patch.object(subject, "_asset_preflight"):
            manifest = subject.export_bundle(self.source, output)
        return output, manifest

    def test_export_is_exact_allowlist_with_canonical_hash_manifest(self):
        output, manifest = self.export()
        verified = subject.verify_bundle(output)
        self.assertEqual(verified, manifest)
        self.assertEqual(
            {path.relative_to(output).as_posix() for path in output.rglob("*") if path.is_file()},
            {relative for _, relative in subject.BUNDLE_FILES} | {subject.MANIFEST_NAME})
        records = manifest["files"]
        identity = hashlib.sha256(subject._json_bytes(records)).hexdigest()
        self.assertEqual(manifest["bundle_identity_sha256"], identity)
        self.assertNotIn("fixture-", (output / subject.MANIFEST_NAME).read_text())

    def test_missing_extra_changed_and_noncanonical_bundles_fail(self):
        output, _ = self.export()
        target = output / subject.BUNDLE_FILES[0][1]
        target.write_bytes(b"changed")
        with self.assertRaisesRegex(subject.DeploymentError, "integrity"):
            subject.verify_bundle(output)
        output, _ = self._fresh_export("second")
        (output / "unapproved.txt").write_text("no")
        with self.assertRaisesRegex(subject.DeploymentError, "unapproved"):
            subject.verify_bundle(output)
        output, _ = self._fresh_export("third")
        manifest = json.loads((output / subject.MANIFEST_NAME).read_text())
        (output / subject.MANIFEST_NAME).write_text(json.dumps(manifest, indent=2))
        with self.assertRaisesRegex(subject.DeploymentError, "canonical"):
            subject.verify_bundle(output)

    def _fresh_export(self, name):
        output = self.root / name
        with patch.object(subject, "_asset_preflight"):
            return output, subject.export_bundle(self.source, output)

    def test_source_and_bundle_symlinks_are_rejected(self):
        relative = subject.BUNDLE_FILES[0][1]
        path = self.source / relative
        original = path.with_suffix(".real")
        path.rename(original)
        path.symlink_to(original)
        with patch.object(subject, "_asset_preflight"):
            with self.assertRaisesRegex(subject.DeploymentError, "symlink"):
                subject.export_bundle(self.source, self.root / "linked-source")
        path.unlink()
        path.write_bytes(b"restored")
        output, _ = self.export()
        extra = output / subject.BUNDLE_FILES[1][1]
        real = extra.with_suffix(".real")
        extra.rename(real)
        extra.symlink_to(real)
        with self.assertRaisesRegex(subject.DeploymentError, "symlink"):
            subject.verify_bundle(output)

    def test_existing_output_is_never_overwritten(self):
        output = self.root / "exists"
        output.mkdir()
        sentinel = output / "keep"
        sentinel.write_text("owner data")
        with patch.object(subject, "_asset_preflight"):
            with self.assertRaisesRegex(subject.DeploymentError, "new output"):
                subject.export_bundle(self.source, output)
        self.assertEqual(sentinel.read_text(), "owner data")


class DeploymentSettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.volume = Path(self.temp.name) / "volume"
        (self.volume / "private").mkdir(parents=True)
        (self.volume / "private/invites.json").write_text("{}")

    def environment(self):
        return {
            "RAILWAY_VOLUME_MOUNT_PATH": str(self.volume),
            "PORT": "8877",
            "BIBLE_BETA_ORIGIN": "https://beta.example.test",
            "TINKER_API_KEY": "synthetic-secret-never-output",
        }

    def test_settings_bind_public_port_and_keep_private_paths_on_volume(self):
        settings = subject.deployment_settings(self.environment())
        self.assertEqual(settings["port"], 8877)
        self.assertEqual(settings["origin"], "https://beta.example.test")
        self.assertEqual(settings["database"], self.volume / "state/beta.sqlite3")
        self.assertFalse(settings["streaming"])
        self.assertNotIn("TINKER_API_KEY", settings)

        enabled = self.environment()
        enabled["MEFORASH_STREAMING"] = "1"
        self.assertTrue(subject.deployment_settings(enabled)["streaming"])

    def test_streaming_flag_accepts_only_exact_zero_or_one(self):
        for value in ("", "true", "false", "yes", "2", " 1"):
            environment = self.environment()
            environment["MEFORASH_STREAMING"] = value
            with self.subTest(value=value):
                with self.assertRaisesRegex(subject.DeploymentError,
                                            "exactly 0 or 1"):
                    subject.deployment_settings(environment)

    def test_missing_secret_http_origin_and_paths_outside_volume_fail_closed(self):
        cases = []
        missing = self.environment(); missing.pop("TINKER_API_KEY"); cases.append(missing)
        http = self.environment(); http["BIBLE_BETA_ORIGIN"] = "http://beta.example.test"; cases.append(http)
        outside = self.environment(); outside["BIBLE_BETA_DATABASE"] = str(self.volume.parent / "db"); cases.append(outside)
        bad_port = self.environment(); bad_port["PORT"] = "not-a-port"; cases.append(bad_port)
        for environment in cases:
            with self.subTest(environment=set(environment)):
                with self.assertRaises(subject.DeploymentError):
                    subject.deployment_settings(environment)

    def test_symlinked_private_config_is_rejected(self):
        invite = self.volume / "private/invites.json"
        real = self.volume / "private/real.json"
        invite.rename(real)
        invite.symlink_to(real)
        with self.assertRaisesRegex(subject.DeploymentError, "non-symlink"):
            subject.deployment_settings(self.environment())

    def test_tokenizer_mount_uses_verified_bundle_and_refuses_overwrite(self):
        bundle = self.volume / "bundle"
        tokenizer = bundle / "data/raw/tokenizers/inkling"
        tokenizer.mkdir(parents=True)
        (tokenizer / "tokenizer.json").write_text("fixture")
        image = self.volume.parent / "image"
        image.mkdir()
        link = subject.install_tokenizer_mount(bundle, image_root=image)
        self.assertTrue(link.is_symlink())
        self.assertEqual((link / "inkling/tokenizer.json").read_text(), "fixture")
        self.assertEqual(subject.install_tokenizer_mount(bundle, image_root=image), link)
        link.unlink()
        link.mkdir()
        with self.assertRaisesRegex(subject.DeploymentError, "start empty"):
            subject.install_tokenizer_mount(bundle, image_root=image)

    def test_setup_handler_exposes_only_health_and_never_needs_runtime_files(self):
        with closing(socket.socket()) as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        server = subject.beta_server.BetaHTTPServer(
            ("127.0.0.1", port), subject.setup_handler())
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
            connection.request("GET", "/health")
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(json.loads(response.read()),
                             {"status": "setup", "model_ready": False})
            connection.close()
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
            connection.request("POST", "/api/login", body=b"secret")
            response = connection.getresponse()
            self.assertEqual(response.status, 503)
            self.assertNotIn(b"secret", response.read())
            connection.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(2)

    def test_setup_port_validation_needs_no_volume_origin_or_credential(self):
        self.assertEqual(subject._port({"PORT": "8877", "MEFORASH_SETUP_ONLY": "1"}), 8877)
        for value in ("", "80", "not-a-port"):
            with self.assertRaises(subject.DeploymentError):
                subject._port({"PORT": value})


if __name__ == "__main__":
    unittest.main()
