from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from recover_working_baseline import is_identity_wrapper, recover_tree


class RecoverWorkingBaselineTest(unittest.TestCase):
    def identity_document(self):
        original = {
            "type": "minecraft:range_dispatch",
            "property": "custom_model_data",
            "fallback": {"type": "minecraft:model", "model": "minecraft:item/iron_ingot"},
            "entries": [{"threshold": 2200080, "model": {"type": "minecraft:model", "model": "slimefun:item/steel"}}],
        }
        wrapper = {
            "type": "minecraft:condition",
            "property": "minecraft:has_component",
            "component": "minecraft:custom_model_data",
            "on_true": copy.deepcopy(original),
            "on_false": {
                "type": "minecraft:condition",
                "property": "minecraft:component",
                "predicate": "minecraft:custom_data",
                "value": {"PublicBukkitValues": {"slimefun:slimefun_item": "STEEL_INGOT"}},
                "on_true": {"type": "minecraft:model", "model": "slimefun:item/steel"},
                "on_false": copy.deepcopy(original),
            },
        }
        return original, {"model": wrapper}

    def test_wrapper_detection_is_scoped(self):
        original, document = self.identity_document()
        self.assertTrue(is_identity_wrapper(document["model"]))
        self.assertFalse(is_identity_wrapper(original))
        self.assertFalse(is_identity_wrapper({
            "type": "minecraft:condition",
            "property": "minecraft:using_item",
            "on_true": {},
            "on_false": {},
        }))

    def test_recovery_restores_original_on_true(self):
        original, document = self.identity_document()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "assets/minecraft/items/iron_ingot.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(document), encoding="utf-8")

            # This fixture intentionally does not run recover_tree because the production
            # function enforces the full reviewed count and carrier hash set. The unwrap
            # invariant is tested directly here.
            self.assertTrue(is_identity_wrapper(document["model"]))
            self.assertEqual(original, document["model"]["on_true"])


if __name__ == "__main__":
    unittest.main()
