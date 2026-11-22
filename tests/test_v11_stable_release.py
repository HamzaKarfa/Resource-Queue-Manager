"""Stable v1.1.0 metadata and one-time publication guard validation.

CI must reject an accidental candidate tag or a publication workflow that
can run on PRs, arbitrary pushes or unreviewed commits.
"""

import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "custom_components" / "resource_queue_manager"
WORKFLOW = ROOT / ".github" / "workflows" / "publish-v1.1-approved-merge.yml"


class StableReleaseTests(unittest.TestCase):
    def test_manifest_and_stable_notes_match(self):
        manifest = json.loads((INTEGRATION / "manifest.json").read_text("utf-8"))
        self.assertEqual(manifest["version"], "1.1.0")
        self.assertEqual(manifest["domain"], "resource_queue_manager")
        self.assertEqual(manifest["integration_type"], "service")
        self.assertTrue(manifest["config_flow"])
        notes = (ROOT / "docs" / "releases" / "v1.1.0.md").read_text("utf-8")
        self.assertTrue(notes.startswith("# Resource Queue Manager — v1.1.0"))
        for forbidden in ("- [ ]", "NOT PUBLISHED", "STATUS: PREPARED", "(draft)"):
            self.assertNotIn(forbidden, notes)
        for expected in (
            "Weighted", "Backfill", "Count", "migration",
            "Home Assistant", "resume",
        ):
            self.assertIn(expected, notes)

    def test_release_workflow_is_guarded_to_authorized_pr32_main_merge(self):
        source = WORKFLOW.read_text("utf-8")
        for required in (
            "branches:", "      - main",
            "release: authorize v1.1.0 stable (PR #32)",
            "refs/heads/main",
            "git rev-list --parents -n 1 HEAD",
            "gh pr view 32",
            'manifest["version"] == "1.1.0"',
            "python -m unittest discover -s tests -v",
            'python -m pytest -q tests/ha',
            '"3.13"', '"3.14"',
            "hacs/action@main", "home-assistant/actions/hassfest@master",
            "gh release create v1.1.0", "--target", '"$GITHUB_SHA"',
            "--latest", "--notes-file docs/releases/v1.1.0.md",
            "refs/tags/v1.1.0",
        ):
            # Tag non-existence check uses the GitHub /git/ref/tags path.
            if required == "refs/tags/v1.1.0":
                self.assertIn("git/ref/tags/v1.1.0", source)
            else:
                self.assertIn(required, source, required)
        self.assertNotIn("workflow_dispatch:", source)
        self.assertNotIn("pull_request:", source)
        self.assertNotIn("schedule:", source)
        self.assertNotIn("--prerelease", source)
        self.assertIn("isPrerelease", source)

    def test_rc_publish_workflows_remain_tagged_history_only(self):
        for filename in (
            "publish-v1.1-rc1-approved.yml",
            "publish-v1.1-rc2-approved.yml",
        ):
            self.assertFalse(
                (ROOT / ".github" / "workflows" / filename).exists(),
                f"Archived prerelease workflow should not ship on main: {filename}",
            )

    def test_stable_readmes_use_public_release_notes(self):
        for filename in ("README.md", "README.fr.md"):
            text = (ROOT / filename).read_text("utf-8")
            self.assertIn("docs/releases/v1.1.0.md", text)
            self.assertIn("docs/MIGRATION_v1.0_to_v1.1.md", text)
            self.assertIn("Backfill", text)
            self.assertNotIn("docs/releases/v1.1.0-draft.md", text)


if __name__ == "__main__":
    unittest.main()
