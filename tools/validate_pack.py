from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import PurePosixPath

REQUIRED_NAMESPACES = {
    "minecraft",
    "slimefun",
    "pylon",
    "rebar",
    "rebarmobs",
    "magic",
    "mmoitems_pack",
    "iaweapons",
    "mcicons",
}

FORBIDDEN_VANILLA_OVERRIDES = {
    "assets/minecraft/models/item/golden_sword.json",
    "assets/minecraft/textures/item/golden_sword.png",
    "assets/minecraft/textures/item/chainmail_helmet.png",
    "assets/minecraft/textures/item/chainmail_chestplate.png",
    "assets/minecraft/textures/item/chainmail_leggings.png",
    "assets/minecraft/textures/item/chainmail_boots.png",
}

REQUIRED_FILES = {
    "pack.mcmeta",
    "pack.png",
    "assets/minecraft/atlases/items.json",
    "assets/minecraft/atlases/blocks.json",
    "assets/minecraft/items/player_head.json",
    "assets/minecraft/items/golden_sword.json",
    "assets/minecraft/items/chainmail_helmet.json",
    "assets/minecraft/items/chainmail_chestplate.json",
    "assets/minecraft/items/chainmail_leggings.json",
    "assets/minecraft/items/chainmail_boots.json",
    "sfl_26_1_plus/assets/minecraft/items/golden_sword.json",
}


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def parse_json(zf: zipfile.ZipFile, name: str, errors: list[str]):
    try:
        return json.loads(zf.read(name))
    except KeyError:
        fail(errors, f"missing JSON file: {name}")
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail(errors, f"invalid JSON {name}: {exc}")
    return None


def walk(obj):
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from walk(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from walk(value)


def model_refs(obj) -> set[str]:
    refs: set[str] = set()
    for node in walk(obj):
        if node.get("type") in {"model", "minecraft:model"}:
            model = node.get("model")
            if isinstance(model, str):
                refs.add(model)
    return refs


def has_player_head_fallback(obj) -> bool:
    for node in walk(obj):
        if node.get("type") == "minecraft:special":
            model = node.get("model")
            if isinstance(model, dict) and model.get("type") == "minecraft:player_head":
                return True
    return False


def check_pack_meta(meta, errors: list[str]) -> None:
    if not isinstance(meta, dict) or not isinstance(meta.get("pack"), dict):
        fail(errors, "pack.mcmeta does not contain a pack object")
        return

    pack = meta["pack"]
    pack_format = pack.get("pack_format")
    if not isinstance(pack_format, int) or pack_format < 75:
        fail(errors, f"pack_format must be >= 75, got {pack_format!r}")

    min_format = pack.get("min_format")
    if min_format not in (75, [75, 0]):
        fail(errors, f"min_format must remain 75/[75,0], got {min_format!r}")

    for node in walk(meta):
        if "formats" in node:
            fail(errors, "deprecated 'formats' key found in pack.mcmeta")
            break


def check_item_atlas(atlas, errors: list[str]) -> None:
    if not isinstance(atlas, dict):
        return
    for i, source in enumerate(atlas.get("sources", [])):
        if not isinstance(source, dict):
            continue
        source_dir = source.get("source")
        resource = source.get("resource")
        sprite = source.get("sprite")

        # Regression guard: this broke every placed block during 26.x testing.
        if source.get("type") in {"directory", "minecraft:directory"} and source_dir == "block":
            fail(errors, f"item atlas source #{i} imports the block directory")
        for value in (resource, sprite):
            if isinstance(value, str) and (":block/" in value or value.startswith("minecraft:block/")):
                fail(errors, f"item atlas source #{i} registers a block sprite: {value}")


def check_block_atlas(atlas, errors: list[str]) -> None:
    if not isinstance(atlas, dict):
        return
    sources = atlas.get("sources", [])
    if not sources:
        fail(errors, "block atlas has no custom sources")
        return
    for i, source in enumerate(sources):
        if not isinstance(source, dict):
            continue
        source_dir = source.get("source")
        resource = source.get("resource")
        sprite = source.get("sprite")
        if source.get("type") in {"directory", "minecraft:directory"} and source_dir == "item":
            fail(errors, f"block atlas source #{i} imports the item directory")
        for value in (resource, sprite):
            if isinstance(value, str) and ":item/" in value:
                fail(errors, f"block atlas source #{i} registers an item sprite: {value}")


def check_chainmail(zf: zipfile.ZipFile, errors: list[str]) -> None:
    for piece in ("helmet", "chestplate", "leggings", "boots"):
        name = f"assets/minecraft/items/chainmail_{piece}.json"
        data = parse_json(zf, name, errors)
        if data is None:
            continue
        expected = f"minecraft:item/chainmail_{piece}"
        if expected not in model_refs(data):
            fail(errors, f"{name} no longer contains the vanilla fallback {expected}")


def check_golden_sword(zf: zipfile.ZipFile, errors: list[str]) -> None:
    required_models = {
        "pylon:item/combat/bronze_sword",
        "iaweapons:ak47",
        "iaweapons:hand_gun",
        "iaweapons:revolver",
        "slimefun:slimefun/weapons/blade_of_vampires",
        "extra_gear:swords/gilded_iron_sword",
        "minecraft:item/golden_sword",
    }
    for name in (
        "assets/minecraft/items/golden_sword.json",
        "sfl_26_1_plus/assets/minecraft/items/golden_sword.json",
    ):
        data = parse_json(zf, name, errors)
        if data is None:
            continue
        refs = model_refs(data)
        missing = sorted(required_models - refs)
        if missing:
            fail(errors, f"{name} lost required Golden Sword mappings: {', '.join(missing)}")


def validate(path: str, expected_sha256: str | None = None) -> list[str]:
    errors: list[str] = []
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    actual_sha256 = digest.hexdigest()

    if expected_sha256 and actual_sha256.lower() != expected_sha256.lower():
        fail(errors, f"SHA-256 mismatch: expected {expected_sha256}, got {actual_sha256}")

    try:
        zf = zipfile.ZipFile(path)
    except zipfile.BadZipFile as exc:
        return [f"invalid ZIP: {exc}"]

    with zf:
        bad = zf.testzip()
        if bad:
            fail(errors, f"ZIP CRC failure: {bad}")

        names = {n for n in zf.namelist() if not n.endswith("/")}
        for name in sorted(REQUIRED_FILES - names):
            fail(errors, f"missing required file: {name}")
        for name in sorted(FORBIDDEN_VANILLA_OVERRIDES & names):
            fail(errors, f"forbidden vanilla override reintroduced: {name}")

        namespaces = {
            PurePosixPath(n).parts[1]
            for n in names
            if n.startswith("assets/") and len(PurePosixPath(n).parts) >= 3
        }
        for namespace in sorted(REQUIRED_NAMESPACES - namespaces):
            fail(errors, f"required namespace missing: assets/{namespace}/")

        meta = parse_json(zf, "pack.mcmeta", errors)
        if meta is not None:
            check_pack_meta(meta, errors)

        item_atlas = parse_json(zf, "assets/minecraft/atlases/items.json", errors)
        if item_atlas is not None:
            check_item_atlas(item_atlas, errors)

        block_atlas = parse_json(zf, "assets/minecraft/atlases/blocks.json", errors)
        if block_atlas is not None:
            check_block_atlas(block_atlas, errors)

        head = parse_json(zf, "assets/minecraft/items/player_head.json", errors)
        if head is not None and not has_player_head_fallback(head):
            fail(errors, "player_head.json lost the native minecraft:player_head fallback")

        check_golden_sword(zf, errors)
        check_chainmail(zf, errors)

    print(f"SHA-256 {actual_sha256}  {path}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate the Slimefun Legacy resource-pack invariants."
    )
    parser.add_argument("pack", help="Path to SlimefunLegacyRP.zip")
    parser.add_argument("--sha256", help="Optional exact SHA-256 expected for this candidate")
    args = parser.parse_args()

    errors = validate(args.pack, args.sha256)
    if errors:
        print("Validation failed:", file=sys.stderr)
        for error in errors:
            print(f" - {error}", file=sys.stderr)
        return 1

    print("Resource-pack validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
