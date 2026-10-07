"""Build client-only texture rules from existing Slimefun persistent identities.

The numeric reference is build input, never a server configuration to install.
Existing explicit model components retain the entire original selector tree.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

MAX_RULES = 64  # Keep client JSON/codec nesting bounded; fail closed on growth.
ITEM_KEY = "slimefun:slimefun_item"
GUIDE_KEY = "slimefun:slimefun_guide_mode"


def kind(value: str | None) -> str | None:
    return value.removeprefix("minecraft:") if isinstance(value, str) else value


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def numeric_models(model: dict) -> dict[int, dict]:
    """Only exact index-zero, unscaled thresholds are eligible references."""
    found: dict[int, dict] = {}
    for node in walk(model):
        if (kind(node.get("type")) != "range_dispatch"
                or kind(node.get("property")) != "custom_model_data"
                or node.get("index", 0) != 0 or node.get("scale", 1) != 1):
            continue
        for entry in node.get("entries", []):
            number = entry["threshold"]
            if isinstance(number, bool) or not isinstance(number, (int, float)):
                raise ValueError(f"invalid model threshold: {number!r}")
            if int(number) != number:
                continue
            number = int(number)
            if number in found and found[number] != entry["model"]:
                raise ValueError(f"ambiguous model threshold: {number}")
            found[number] = entry["model"]
    return found


def is_native_head(model: dict) -> bool:
    return (kind(model.get("type")) == "special"
            and kind(model.get("model", {}).get("type")) == "player_head")


def without_model_data(model: dict) -> dict:
    while (kind(model.get("type")) in {"range_dispatch", "select"}
           and kind(model.get("property")) == "custom_model_data"):
        model = model["fallback"]
    return model


def condition(key: str, value: str, matched: dict, fallback: dict) -> dict:
    # Partial NBT predicate: backpack UUIDs, addon tags, etc. do not prevent a match.
    return {
        "type": "minecraft:condition",
        "property": "minecraft:component",
        "predicate": "minecraft:custom_data",
        "value": {"PublicBukkitValues": {key: value}},
        "on_true": copy.deepcopy(matched),
        "on_false": fallback,
    }


def add_identity_rules(document: dict, mappings: dict[str, int], carrier: str):
    original = document["model"]
    models = numeric_models(original)
    rules = []
    native_heads = []
    for item_id, number in sorted(mappings.items()):
        model = models.get(number)
        if model is None:
            continue
        if is_native_head(model):
            if carrier != "player_head" or not is_native_head(without_model_data(original)):
                raise ValueError(f"unexpected native head carrier: {carrier}/{item_id}")
            # Head skins are already stored in the profile. Do not build an 826-deep
            # identity chain or substitute a static head for a player's real profile.
            native_heads.append(item_id)
            continue
        rules.append((ITEM_KEY, item_id, model))
        if item_id == "SLIMEFUN_GUIDE":
            # Real guides use their longstanding guide-mode key, not an item ID.
            for mode in ("SURVIVAL_MODE", "CHEAT_MODE"):
                rules.append((GUIDE_KEY, mode, model))
    if len(rules) > MAX_RULES:
        raise ValueError(f"{carrier}: {len(rules)} identity rules exceed limit {MAX_RULES}")
    if not rules:
        return document, [], native_heads

    fallback = copy.deepcopy(original)
    for key, value, model in reversed(rules):
        fallback = condition(key, value, model, fallback)
    result = copy.deepcopy(document)
    result["model"] = {
        "type": "minecraft:condition",
        "property": "minecraft:has_component",
        "component": "minecraft:custom_model_data",
        "on_true": copy.deepcopy(original),
        "on_false": fallback,
    }
    return result, [value for key, value, _ in rules if key == ITEM_KEY], native_heads


def apply_identity_rules(root: Path, reference: Path) -> dict:
    data = json.loads(reference.read_text(encoding="utf-8"))
    mappings = data["models"]
    if not mappings or any(not isinstance(k, str) or type(v) is not int or v <= 0
                           for k, v in mappings.items()):
        raise ValueError("identity reference must contain positive integer model numbers")

    report = {"source": data["source"], "changed_files": {}, "native_head_ids": [],
              "unmatched_ids": []}
    seen = set()
    heads = set()
    # Covers base item definitions and every existing version overlay independently.
    for path in sorted(root.rglob("assets/minecraft/items/*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        result, matched, native = add_identity_rules(document, mappings, path.stem)
        seen.update(matched)
        heads.update(native)
        if matched:
            path.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n",
                            encoding="utf-8")
            report["changed_files"][path.relative_to(root).as_posix()] = matched
    report["native_head_ids"] = sorted(heads)
    report["unmatched_ids"] = sorted(set(mappings) - seen - heads)
    report["textured_ids"] = sorted(seen)
    return report
