"""Check translation coverage for v1.1 configuration and service fields."""

import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "resource_queue_manager"


def leaf_keys(payload, prefix=()):
    keys = set()
    for key, value in payload.items():
        name = (*prefix, key)
        if isinstance(value, dict):
            keys |= leaf_keys(value, name)
        else:
            keys.add(name)
    return keys


class V11LocalizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.english = json.loads((ROOT / "strings.json").read_text(encoding="utf-8"))
        cls.translation_en = json.loads(
            (ROOT / "translations" / "en.json").read_text(encoding="utf-8")
        )
        cls.french = json.loads(
            (ROOT / "translations" / "fr.json").read_text(encoding="utf-8")
        )

    def test_en_and_fr_keys_match_canonical_strings(self):
        required_keys = leaf_keys(self.english)
        self.assertEqual(leaf_keys(self.translation_en), required_keys)
        self.assertEqual(leaf_keys(self.french), required_keys)

    def test_required_v11_form_fields_and_event_descriptions(self):
        for values in (self.english, self.translation_en, self.french):
            for section, step in (("config", "user"), ("options", "init")):
                for field in ("capacity_mode", "recurrence_mode"):
                    self.assertIn(field, values[section]["step"][step]["data"])
                    self.assertIn(
                        field,
                        values[section]["step"][step]["data_description"],
                    )
            self.assertIn("weights", values["config"]["step"])
            self.assertIn("weights", values["options"]["step"])
            self.assertIn("engine_data", values["services"]["request"]["fields"])
            self.assertIn("invalid_weights", values["config"]["error"])
            self.assertIn("invalid_weights", values["options"]["error"])
            self.assertIn("recurrence_mode_in_use", values["options"]["error"])

    def test_all_localized_leaves_are_nonempty_strings(self):
        for locale in (self.english, self.translation_en, self.french):
            for path in leaf_keys(locale):
                value = locale
                for segment in path:
                    value = value[segment]
                self.assertIsInstance(value, str, path)
                self.assertTrue(value.strip(), path)


if __name__ == "__main__":
    unittest.main()
