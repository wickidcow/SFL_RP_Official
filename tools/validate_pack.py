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

TALISMAN_EMERALD_MODELS = {
    2200529: "slimefun:caveman_talisman",
    2200530: "slimefun:ender_caveman_talisman",
    2200531: "slimefun:wise_talisman",
    2200532: "slimefun:ender_wise_talisman",
    2200545: "slimefun:farmer_talisman",
    2200546: "slimefun:ender_farmer_talisman",
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


TALISMAN_ALIAS_MODELS = {
    "assets/slimefun/models/slimefun/talisman1/caveman.json":
        "_slimefun:slimefun/talisman1/caveman",
    "assets/slimefun/models/slimefun/talisman2/caveman.json":
        "_slimefun:slimefun/talisman2/caveman",
    "assets/slimefun/models/slimefun/talisman1/wise.json":
        "_slimefun:slimefun/talisman1/wise",
    "assets/slimefun/models/slimefun/talisman2/wise.json":
        "_slimefun:slimefun/talisman2/wise",
    "assets/slimefun/models/slimefun/talisman1/farmer.json":
        "_slimefun:slimefun/talisman1/farmer",
    "assets/slimefun/models/slimefun/talisman2/farmer.json":
        "_slimefun:slimefun/talisman2/farmer",
}


def texture_refs(obj) -> set[str]:
    refs: set[str] = set()
    for node in walk(obj):
        textures = node.get("textures")
        if not isinstance(textures, dict):
            continue
        for value in textures.values():
            if isinstance(value, str) and not value.startswith("#"):
                refs.add(value)
    return refs


def slimefun_sprite_aliases(zf: zipfile.ZipFile, names: set[str], errors: list[str]) -> dict[str, str]:
    aliases: dict[str, str] = {}

    for name in sorted(n for n in names if n.endswith("assets/minecraft/atlases/items.json")):
        atlas = parse_json(zf, name, errors)
        if not isinstance(atlas, dict):
            continue

        for source in atlas.get("sources", []):
            if not isinstance(source, dict):
                continue
            if source.get("type") not in {"single", "minecraft:single"}:
                continue

            resource = source.get("resource")
            sprite = source.get("sprite")
            if not (
                isinstance(resource, str)
                and isinstance(sprite, str)
                and resource.startswith("slimefun:")
                and sprite.startswith("_slimefun:")
            ):
                continue

            previous = aliases.get(resource)
            if previous is not None and previous != sprite:
                fail(
                    errors,
                    f"conflicting Slimefun item-atlas aliases for {resource}: {previous} vs {sprite}",
                )
            else:
                aliases[resource] = sprite

    return aliases


def check_slimefun_model_aliases(zf: zipfile.ZipFile, names: set[str], errors: list[str]) -> None:
    aliases = slimefun_sprite_aliases(zf, names, errors)
    if not aliases:
        # The modern v4 layout stores Slimefun sprites under item/ and does not need
        # the historical _slimefun alias layer. There is nothing to validate here.
        return

    mismatches: list[tuple[str, str, str]] = []
    for name in sorted(
        n for n in names if n.startswith("assets/slimefun/models/") and n.endswith(".json")
    ):
        model = parse_json(zf, name, errors)
        if not isinstance(model, dict):
            continue

        for ref in sorted(texture_refs(model)):
            expected = aliases.get(ref)
            if expected is not None:
                mismatches.append((name, ref, expected))

    if mismatches:
        examples = "; ".join(
            f"{name}: {actual} -> {expected}"
            for name, actual, expected in mismatches[:8]
        )
        extra = "" if len(mismatches) <= 8 else f"; ... {len(mismatches) - 8} more"
        fail(
            errors,
            "Slimefun models reference atlas resources instead of their registered "
            f"_slimefun sprite aliases ({len(mismatches)} reference(s)): {examples}{extra}",
        )

    # Regression guard for the six exact models reported broken on standalone 26.3.
    for name, expected in TALISMAN_ALIAS_MODELS.items():
        if name not in names:
            continue
        model = parse_json(zf, name, errors)
        if not isinstance(model, dict):
            continue
        refs = texture_refs(model)
        if expected not in refs:
            fail(errors, f"{name} does not reference required sprite alias {expected}")


def validate_aliases_only(path: str, expected_sha256: str | None = None) -> list[str]:
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
        check_slimefun_model_aliases(zf, names, errors)

    print(f"SHA-256 {actual_sha256}  {path}")
    return errors


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


def custom_model_entries(obj) -> dict[int, str]:
    entries: dict[int, str] = {}
    for node in walk(obj):
        if node.get("type") not in {"range_dispatch", "minecraft:range_dispatch"}:
            continue
        if node.get("property") != "minecraft:custom_model_data":
            continue
        for entry in node.get("entries", []):
            if not isinstance(entry, dict):
                continue
            threshold = entry.get("threshold")
            model = entry.get("model")
            if isinstance(threshold, (int, float)) and isinstance(model, dict):
                ref = model.get("model")
                if isinstance(ref, str):
                    entries[int(threshold)] = ref
    return entries


def check_model_file_exists(zf: zipfile.ZipFile, ref: str, errors: list[str], context: str) -> None:
    if ":" not in ref:
        namespace, path = "minecraft", ref
    else:
        namespace, path = ref.split(":", 1)
    if namespace == "minecraft":
        return
    name = f"assets/{namespace}/models/{path}.json"
    if name not in zf.namelist():
        fail(errors, f"{context} points to missing model: {ref} ({name})")


def check_texture_refs(zf: zipfile.ZipFile, model_ref: str, errors: list[str], seen: set[str] | None = None) -> None:
    if seen is None:
        seen = set()
    if model_ref in seen or ":" not in model_ref:
        return
    seen.add(model_ref)
    namespace, path = model_ref.split(":", 1)
    if namespace == "minecraft":
        return
    name = f"assets/{namespace}/models/{path}.json"
    data = parse_json(zf, name, errors)
    if not isinstance(data, dict):
        return

    parent = data.get("parent")
    if isinstance(parent, str) and ":" in parent and not parent.startswith("minecraft:"):
        check_model_file_exists(zf, parent, errors, name)
        check_texture_refs(zf, parent, errors, seen)

    textures = data.get("textures", {})
    if isinstance(textures, dict):
        for texture in textures.values():
            if not isinstance(texture, str) or texture.startswith("#") or ":" not in texture:
                continue
            tex_ns, tex_path = texture.split(":", 1)
            if tex_ns == "minecraft":
                continue
            png = f"assets/{tex_ns}/textures/{tex_path}.png"
            if png not in zf.namelist():
                fail(errors, f"{name} points to missing texture: {texture} ({png})")


def check_talisman_models(zf: zipfile.ZipFile, errors: list[str]) -> None:
    candidates = [
        name for name in zf.namelist()
        if name == "assets/minecraft/items/emerald.json"
        or name.endswith("/assets/minecraft/items/emerald.json")
    ]
    if not candidates:
        fail(errors, "no emerald item definition found for Slimefun talismans")
        return

    effective = {}
    for name in sorted(candidates, key=lambda value: (value.count("/"), value)):
        data = parse_json(zf, name, errors)
        if isinstance(data, dict):
            effective.update(custom_model_entries(data))

    for model_id, expected_ref in TALISMAN_EMERALD_MODELS.items():
        actual = effective.get(model_id)
        if actual is None:
            fail(errors, f"emerald item definition is missing talisman CustomModelData {model_id} -> {expected_ref}")
            continue
        if actual != expected_ref:
            fail(errors, f"emerald CustomModelData {model_id} points to {actual}, expected {expected_ref}")
            continue
        check_model_file_exists(zf, actual, errors, f"emerald CustomModelData {model_id}")
        check_texture_refs(zf, actual, errors)


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
        check_talisman_models(zf, errors)
        check_slimefun_model_aliases(zf, names, errors)

    print(f"SHA-256 {actual_sha256}  {path}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate the Slimefun Legacy resource-pack invariants."
    )
    parser.add_argument("pack", help="Path to SlimefunLegacyRP.zip")
    parser.add_argument("--sha256", help="Optional exact SHA-256 expected for this candidate")
    parser.add_argument(
        "--aliases-only",
        action="store_true",
        help="Validate only ZIP integrity and Slimefun item-atlas sprite aliases",
    )
    args = parser.parse_args()

    errors = (
        validate_aliases_only(args.pack, args.sha256)
        if args.aliases_only
        else validate(args.pack, args.sha256)
    )
    if errors:
        print("Validation failed:", file=sys.stderr)
        for error in errors:
            print(f" - {error}", file=sys.stderr)
        return 1

    print("Resource-pack validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
