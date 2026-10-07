import copy
import json
import tempfile
import unittest
from pathlib import Path

from item_identity_rules import (
    GUIDE_KEY, ITEM_KEY, MAX_RULES, add_identity_rules, apply_identity_rules,
)


VANILLA = {"type": "minecraft:model", "model": "minecraft:item/iron_ingot"}
STEEL = {"type": "minecraft:model", "model": "slimefun:item/steel"}
PYLON = {"type": "minecraft:model", "model": "pylon:item/ingot"}


def fixture():
    return {"hand_animation_on_swap": False, "model": {
        "type": "minecraft:select", "property": "minecraft:custom_model_data",
        "cases": [{"when": "pylon:ingot", "model": PYLON}],
        "fallback": {
            "type": "range_dispatch", "property": "custom_model_data",
            "entries": [{"threshold": 2200080, "model": STEEL}], "fallback": VANILLA,
        },
    }}


def partial_match(expected, actual):
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(k in actual and partial_match(v, actual[k])
                                               for k, v in expected.items())
    return expected == actual


def select(model, components):
    """Small behavior oracle for the four node types used by this fixture."""
    node = model
    while True:
        kind = node["type"].removeprefix("minecraft:")
        prop = node.get("property", "").removeprefix("minecraft:")
        cmd = components.get("minecraft:custom_model_data", {})
        if kind == "condition":
            if prop == "has_component":
                match = node["component"] in components
            else:
                match = partial_match(node["value"], components.get("minecraft:custom_data", {}))
            node = node["on_true" if match else "on_false"]
        elif kind == "select":
            value = next(iter(cmd.get("strings", [])), None)
            node = next((c["model"] for c in node["cases"] if c["when"] == value), node["fallback"])
        elif kind == "range_dispatch":
            value = next(iter(cmd.get("floats", [])), 0)
            eligible = [e for e in node["entries"] if e["threshold"] <= value]
            node = max(eligible, key=lambda e: e["threshold"])["model"] if eligible else node["fallback"]
        else:
            return node


def identity(item_id):
    return {"minecraft:custom_data": {"PublicBukkitValues": {ITEM_KEY: item_id}}}


class IdentityRulesTest(unittest.TestCase):
    def setUp(self):
        self.original = fixture()
        self.updated, self.ids, _ = add_identity_rules(self.original, {"STEEL_INGOT": 2200080}, "iron_ingot")

    def test_existing_item_matches_without_model_data(self):
        item = identity("STEEL_INGOT")
        before = copy.deepcopy(item)
        self.assertEqual(STEEL, select(self.updated["model"], item))
        self.assertEqual(before, item)

    def test_extra_persistent_data_does_not_prevent_match(self):
        item = identity("STEEL_INGOT")
        item["minecraft:custom_data"]["PublicBukkitValues"].update({"slimefun:backpack_id": "uuid", "other:data": 3})
        item["minecraft:custom_data"]["additional"] = "retained"
        self.assertEqual(STEEL, select(self.updated["model"], item))

    def test_vanilla_unknown_and_wrong_namespace_keep_fallback(self):
        for item in ({}, identity("UNRECOGNIZED"),
                     {"minecraft:custom_data": {"PublicBukkitValues": {"other:slimefun_item": "STEEL_INGOT"}}}):
            self.assertEqual(VANILLA, select(self.updated["model"], item))

    def test_explicit_model_data_keeps_original_dispatch(self):
        for cmd in ({"floats": [2200080]}, {"floats": [9]}, {"floats": [0]}, {},
                    {"strings": ["pylon:ingot"]}, {"floats": [123], "strings": ["itemsadder:custom"]}):
            item = identity("STEEL_INGOT")
            item["minecraft:custom_model_data"] = cmd
            self.assertEqual(select(self.original["model"], item), select(self.updated["model"], item))
        self.assertEqual(self.original["model"], self.updated["model"]["on_true"])

    def test_source_and_non_model_fields_are_unchanged(self):
        self.assertEqual(fixture(), self.original)
        self.assertFalse(self.updated["hand_animation_on_swap"])

    def test_aliases_share_existing_artwork(self):
        updated, ids, _ = add_identity_rules(fixture(), {"STEEL_INGOT": 2200080, "ALIAS": 2200080}, "iron_ingot")
        self.assertEqual(["ALIAS", "STEEL_INGOT"], ids)
        self.assertEqual(STEEL, select(updated["model"], identity("ALIAS")))

    def test_guide_modes_use_the_existing_guide_key(self):
        updated, _, _ = add_identity_rules(fixture(), {"SLIMEFUN_GUIDE": 2200080}, "enchanted_book")
        for mode in ("CHEAT_MODE", "SURVIVAL_MODE"):
            item = {"minecraft:custom_data": {"PublicBukkitValues": {GUIDE_KEY: mode}}}
            self.assertEqual(STEEL, select(updated["model"], item))

    def test_native_heads_keep_profile_renderer_without_deep_chain(self):
        native = {"type": "minecraft:special", "base": "minecraft:item/template_skull",
                  "model": {"type": "minecraft:player_head"}}
        original = {"model": {"type": "range_dispatch", "property": "custom_model_data",
                     "fallback": native, "entries": [{"threshold": 7, "model": native}]}}
        updated, ids, heads = add_identity_rules(original, {"BATTERY": 7}, "player_head")
        self.assertEqual(original, updated)
        self.assertEqual([], ids)
        self.assertEqual(["BATTERY"], heads)

    def test_different_index_or_scale_is_not_inferred(self):
        for field, value in (("index", 1), ("scale", 2)):
            original = fixture()
            original["model"]["fallback"][field] = value
            updated, ids, _ = add_identity_rules(original, {"STEEL_INGOT": 2200080}, "iron_ingot")
            self.assertEqual(original, updated)
            self.assertEqual([], ids)

    def test_ambiguous_numbers_fail_closed(self):
        original = fixture()
        original["model"]["fallback"]["entries"].append({"threshold": 2200080, "model": VANILLA})
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            add_identity_rules(original, {"STEEL_INGOT": 2200080}, "iron_ingot")

    def test_excessive_nesting_fails_before_pack_output(self):
        with self.assertRaisesRegex(ValueError, "exceed limit"):
            add_identity_rules(fixture(), {f"ITEM_{i}": 2200080 for i in range(MAX_RULES + 1)}, "iron_ingot")

    def test_base_overlay_coverage_and_untouched_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for prefix in ("", "sfl_26_1_plus/"):
                path = root / (prefix + "assets/minecraft/items/iron_ingot.json")
                path.parent.mkdir(parents=True)
                path.write_text(json.dumps(fixture()))
            unrelated = root / "assets/minecraft/items/diamond.json"
            unrelated.write_bytes(b'{ "model" : {"type":"model","model":"item/diamond"} }')
            before = unrelated.read_bytes()
            reference = root / "reference.json"
            reference.write_text(json.dumps({"source": {}, "models": {"STEEL_INGOT": 2200080, "UNKNOWN": 99}}))
            report = apply_identity_rules(root, reference)
            self.assertEqual(2, len(report["changed_files"]))
            self.assertEqual(["STEEL_INGOT"], report["textured_ids"])
            self.assertEqual(["UNKNOWN"], report["unmatched_ids"])
            self.assertEqual(before, unrelated.read_bytes())


if __name__ == "__main__":
    unittest.main()
