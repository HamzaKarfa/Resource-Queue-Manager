"""Validate release metadata and translation parity without Home Assistant."""

import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "custom_components" / "resource_queue_manager"


def leaf_paths(value, prefix=""):
    """Return all nested translation keys, not the translated wording."""
    if isinstance(value, dict):
        result = set()
        for name, item in value.items():
            path = f"{prefix}.{name}" if prefix else name
            result.update(leaf_paths(item, path))
        return result
    return {prefix}


class ReleaseMetadataTests(unittest.TestCase):
    def test_manifest_matches_hacs_and_release_notes(self):
        manifest = json.loads((INTEGRATION / "manifest.json").read_text("utf-8"))
        hacs = json.loads((ROOT / "hacs.json").read_text("utf-8"))
        version = manifest["version"]
        self.assertRegex(version, r"^\d+\.\d+\.\d+(?:-rc\.\d+)?$")
        self.assertEqual(hacs["name"], manifest["name"])
        self.assertTrue(manifest["config_flow"])
        self.assertTrue((ROOT / "docs" / "releases" / f"v{version}.md").is_file())
        self.assertTrue((ROOT / "docs" / "DEVELOPMENT.md").is_file())
        self.assertTrue((ROOT / "docs" / "MIGRATION_v0.4_to_v1.md").is_file())
        self.assertTrue((ROOT / "docs" / "V1_ARCHITECTURE.md").is_file())

    def test_action_config_entry_selector_can_find_queue_instances(self):
        """The HA frontend picker lists device/hub/service, not helper entries."""
        manifest = json.loads((INTEGRATION / "manifest.json").read_text("utf-8"))
        self.assertEqual(manifest["integration_type"], "service")
        services = (INTEGRATION / "services.yaml").read_text("utf-8")
        self.assertEqual(services.count("integration: resource_queue_manager"), 4)

    def test_english_and_french_ui_keys_match_strings(self):
        original = json.loads((INTEGRATION / "strings.json").read_text("utf-8"))
        reference = leaf_paths(original)
        for name in ("en.json", "fr.json"):
            with self.subTest(locale=name):
                other = json.loads(
                    (INTEGRATION / "translations" / name).read_text("utf-8")
                )
                self.assertEqual(reference, leaf_paths(other))
                for section in ("config", "options", "services"):
                    self.assertIn(section, other)

    def test_no_obsolete_legacy_files_or_docs_references(self):
        """Avoid shipping compatibility wrappers after generic engine migration."""
        self.assertFalse((INTEGRATION / "fifo.py").exists())
        self.assertFalse((ROOT / "tests" / "test_fifo.py").exists())
        self.assertTrue((ROOT / "tests" / "test_engine.py").is_file())
        self.assertFalse((ROOT / ".vscode" / "settings.json").exists())
        dev_guide = (ROOT / "docs" / "DEVELOPMENT.md").read_text("utf-8")
        self.assertNotIn("├── fifo.py", dev_guide)
        self.assertNotIn("├── test_fifo.py", dev_guide)
        self.assertIn("entity_supervision.py", dev_guide)

    def test_v1_release_notes_are_ready_to_publish(self):
        """Stable release must not contain a draft label or unchecked gates."""
        notes = (ROOT / "docs" / "releases" / "v1.0.0.md").read_text("utf-8")
        self.assertIn("# Resource Queue Manager — v1.0.0", notes)
        self.assertIn("/blob/v1.0.0/docs/MIGRATION_v0.4_to_v1.md", notes)
        for marker in ("not yet published", "Prepared release notes", "- [ ]"):
            self.assertNotIn(marker, notes)
        self.assertTrue((ROOT / "docs" / "RELEASE_CHECKLIST_v1.md").is_file())

    def test_v1_release_is_manual_only(self):
        yaml_path = ROOT / ".github" / "workflows" / "publish-v1.yml"
        source = yaml_path.read_text("utf-8")
        self.assertIn("workflow_dispatch:", source)
        self.assertIn("PUBLISH_V1_0_0", source)
        self.assertIn("refs/heads/main", source)
        self.assertIn("docs/releases/v1.0.0.md", source)
        self.assertIsNone(
            re.search(r"(?m)^\s{2}(push|pull_request|schedule):", source)
        )
        self.assertFalse(
            (ROOT / ".github" / "workflows" / "publish-v0.4.0.yml").exists()
        )


if __name__ == "__main__":
    unittest.main()
