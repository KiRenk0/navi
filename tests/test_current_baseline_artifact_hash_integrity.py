"""Narrow QA for current baseline raw artifact-hash integrity."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.tools.current_baseline_regression_check import sha256, verify_artifact_hashes


CASE_ID = "synthetic_case"
SCHEMA_V5 = "current-tpg-baseline-regression/v5"


class CurrentBaselineArtifactHashIntegrityTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory(prefix="baseline_artifact_hash_")
        self.baseline_dir = Path(self._temporary_directory.name)
        (self.baseline_dir / "fields.npz").write_bytes(b"synthetic fields")
        (self.baseline_dir / "summary.json").write_bytes(b'{"status":"synthetic"}\n')
        self.manifest = {
            "manifest_schema": SCHEMA_V5,
            "artifact_hashes_sha256": {
                name: sha256(self.baseline_dir / name)
                for name in ("fields.npz", "summary.json")
            },
        }

    def tearDown(self) -> None:
        temporary_root = self.baseline_dir
        self._temporary_directory.cleanup()
        self.assertFalse(temporary_root.exists())

    def assert_failed_for(self, artifact_name: str, reason: str) -> None:
        ok, errors = verify_artifact_hashes(CASE_ID, self.baseline_dir, self.manifest)
        self.assertFalse(ok)
        self.assertTrue(any(f"case={CASE_ID}" in error for error in errors), errors)
        self.assertTrue(any(f"artifact={artifact_name}" in error for error in errors), errors)
        self.assertTrue(any("registered=" in error and "actual=" in error for error in errors), errors)
        self.assertTrue(any(f"reason={reason}" in error for error in errors), errors)

    def test_valid_fields_and_summary_hashes_pass(self) -> None:
        ok, errors = verify_artifact_hashes(CASE_ID, self.baseline_dir, self.manifest)
        self.assertTrue(ok)
        self.assertEqual(errors, [])

    def test_summary_hash_mismatch_fails(self) -> None:
        self.manifest["artifact_hashes_sha256"]["summary.json"] = "0" * 64
        self.assert_failed_for("summary.json", "artifact-hash-mismatch")

    def test_fields_hash_mismatch_fails(self) -> None:
        self.manifest["artifact_hashes_sha256"]["fields.npz"] = "0" * 64
        self.assert_failed_for("fields.npz", "artifact-hash-mismatch")

    def test_missing_artifact_file_fails(self) -> None:
        (self.baseline_dir / "summary.json").unlink()
        self.assert_failed_for("summary.json", "artifact-file-missing")

    def test_non_lowercase_sha256_digest_fails(self) -> None:
        digest = self.manifest["artifact_hashes_sha256"]["summary.json"]
        self.manifest["artifact_hashes_sha256"]["summary.json"] = digest.upper()
        self.assert_failed_for("summary.json", "registered-digest-not-lowercase-sha256")


if __name__ == "__main__":
    unittest.main()
