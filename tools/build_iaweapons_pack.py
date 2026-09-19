from __future__ import annotations

import argparse
import json
import shutil
import tempfile
import zipfile
from pathlib import Path

OVERLAY = "iaweapons_1_21_11_plus"
CARRIERS = ("crossbow", "golden_sword", "snowball", "stick")

def is_iaweapons_model(obj):
    if isinstance(obj, str):
        return obj.startswith("iaweapons:") or obj.startswith("_iainternal:item_context/iaweapons/")
    if isinstance(obj, dict):
        return any(is_iaweapons_model(v) for v in obj.values())
    if isinstance(obj, list):
        return any(is_iaweapons_model(v) for v in obj)
    return False

def copy_tree(src: Path, dst: Path):
    if not src.exists():
        raise FileNotFoundError(src)
    shutil.copytree(src, dst)

def normalize_resource_aliases(root: Path):
    """Repair ItemsAdder alias namespaces only inside the retained IAWeapons graph."""
    replacements = {
        "_minecraft:": "minecraft:",
        "_b_minecraft:": "minecraft:",
        "_iaweapons:": "iaweapons:",
        "_b_iaweapons:": "iaweapons:",
    }

    def rewrite(obj):
        if isinstance(obj, dict):
            return {key: rewrite(value) for key, value in obj.items()}
        if isinstance(obj, list):
            return [rewrite(value) for value in obj]
        if isinstance(obj, str):
            for prefix, replacement in replacements.items():
                if obj.startswith(prefix):
                    return replacement + obj[len(prefix):]
        return obj

    for path in root.rglob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        fixed = rewrite(data)
        if fixed != data:
            path.write_text(json.dumps(fixed, separators=(",", ":")) + "\n", encoding="utf-8")

def build(source_zip: Path, output_zip: Path):
    with tempfile.TemporaryDirectory(prefix="sfl-iaweapons-") as temp:
        temp = Path(temp)
        source = temp / "source"
        out = temp / "pack"
        source.mkdir()
        out.mkdir()

        with zipfile.ZipFile(source_zip) as zf:
            zf.extractall(source)

        # Keep IAWeapons itself, including models, textures, sounds and sounds.json.
        copy_tree(source / "assets" / "iaweapons", out / "assets" / "iaweapons")

        # Preserve the updated purple Slimefun pack icon from the approved source pack.
        shutil.copy2(source / "pack.png", out / "pack.png")

        # 1.21.11 is resource-pack format 75. Keep the pack loadable on later formats too.
        pack_meta = {
            "pack": {
                "pack_format": 75,
                "min_format": 75,
                "max_format": 9999,
                "description": "SFL IAWeapons Resource Pack • Minecraft 1.21.11+"
            },
            "overlays": {
                "entries": [
                    {
                        "directory": OVERLAY,
                        "min_format": 75,
                        "max_format": 9999
                    }
                ]
            }
        }
        (out / "pack.mcmeta").write_text(json.dumps(pack_meta, indent=2) + "\n", encoding="utf-8")

        # Use the source pack's known-working modern item definitions, but strip every
        # non-IAWeapons CustomModelData mapping so vanilla/Slimefun/Pylon items are untouched.
        source_items = source / "ia_overlay_modern_atlas" / "assets" / "minecraft" / "items"
        dest_items = out / OVERLAY / "assets" / "minecraft" / "items"
        dest_items.mkdir(parents=True, exist_ok=True)

        for name in CARRIERS:
            data = json.loads((source_items / f"{name}.json").read_text(encoding="utf-8"))
            model = data["model"]
            entries = model.get("entries")
            if isinstance(entries, list):
                model["entries"] = [
                    entry for entry in entries
                    if is_iaweapons_model(entry.get("model"))
                ]
            (dest_items / f"{name}.json").write_text(
                json.dumps(data, separators=(",", ":")) + "\n",
                encoding="utf-8"
            )

        # Firework launcher uses ItemsAdder-generated item-context helper models.
        helper_source = (
            source / "ia_overlay_modern_atlas" / "assets" / "_iainternal" /
            "models" / "item_context" / "iaweapons"
        )
        helper_dest = (
            out / OVERLAY / "assets" / "_iainternal" /
            "models" / "item_context" / "iaweapons"
        )
        copy_tree(helper_source, helper_dest)

        extra_source = (
            source / "ia_overlay_modern_atlas" / "assets" / "iaweapons" /
            "models" / "firework_launcher" / "firework_launcher_0.json"
        )
        extra_dest = (
            out / OVERLAY / "assets" / "iaweapons" /
            "models" / "firework_launcher" / "firework_launcher_0.json"
        )
        extra_dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(extra_source, extra_dest)

        # Minimal modern item atlas. Preserve normal vanilla item sprites and add only IAWeapons.
        sources = [{"type": "minecraft:directory", "source": "item", "prefix": "item/"}]
        texture_root = out / "assets" / "iaweapons" / "textures"
        for texture in sorted(texture_root.rglob("*.png")):
            rel = texture.relative_to(texture_root).with_suffix("").as_posix()
            sources.append({
                "type": "minecraft:single",
                "resource": f"iaweapons:{rel}",
                "sprite": f"iaweapons:{rel}"
            })

        atlas = out / OVERLAY / "assets" / "minecraft" / "atlases" / "items.json"
        atlas.parent.mkdir(parents=True, exist_ok=True)
        atlas.write_text(json.dumps({"sources": sources}, separators=(",", ":")) + "\n", encoding="utf-8")

        # Older generated packs can retain private ItemsAdder aliases. Normalize only
        # the two namespaces kept by this trimmed pack before validating the graph.
        normalize_resource_aliases(out)

        (out / "README.txt").write_text(
            "SFL IAWeapons Resource Pack\n"
            "Compatibility: Minecraft Java 1.21.11+; validated through 26.3.\n"
            "Contains only IAWeapons assets plus required carrier item definitions, atlas and helper models.\n"
            "CustomModelData mappings preserved:\n"
            "  crossbow: 10000 shotgun, 10001 firework launcher\n"
            "  golden_sword: 1981823 AK47, 1981824 hand gun, 1981828 revolver\n"
            "  snowball: 9928315 grenade\n"
            "  stick: 10029 clip, 10079 shotgun cartridge, 10080 projectile\n",
            encoding="utf-8"
        )

        validate(out)

        output_zip.parent.mkdir(parents=True, exist_ok=True)
        if output_zip.exists():
            output_zip.unlink()

        with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
            for path in sorted(out.rglob("*")):
                if path.is_file():
                    zf.write(path, path.relative_to(out).as_posix())

def validate(root: Path):
    allowed_namespaces = {"minecraft", "iaweapons", "_iainternal"}

    # Every JSON must parse, and no removed addon namespace may remain.
    for path in root.rglob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))

        def walk(obj):
            if isinstance(obj, dict):
                for value in obj.values():
                    walk(value)
            elif isinstance(obj, list):
                for value in obj:
                    walk(value)
            elif isinstance(obj, str) and ":" in obj:
                namespace = obj.split(":", 1)[0]
                if namespace and all(c.islower() or c.isdigit() or c in "_.-" for c in namespace):
                    if namespace not in allowed_namespaces and not obj.startswith("#"):
                        raise ValueError(f"Removed namespace reference in {path}: {obj}")

        walk(data)

    expected = {
        "crossbow": [10000, 10001],
        "golden_sword": [1981823, 1981824, 1981828],
        "snowball": [9928315],
        "stick": [10029, 10079, 10080],
    }
    item_dir = root / OVERLAY / "assets" / "minecraft" / "items"
    for name, thresholds in expected.items():
        data = json.loads((item_dir / f"{name}.json").read_text(encoding="utf-8"))
        actual = [entry["threshold"] for entry in data["model"].get("entries", [])]
        if actual != thresholds:
            raise ValueError(f"{name} CustomModelData mismatch: {actual} != {thresholds}")

    # Validate IA model parents/textures.
    missing = []
    model_roots = [
        root / "assets" / "iaweapons" / "models",
        root / OVERLAY / "assets" / "_iainternal" / "models",
    ]
    for model_root in model_roots:
        if not model_root.exists():
            continue
        for path in model_root.rglob("*.json"):
            data = json.loads(path.read_text(encoding="utf-8"))
            current_ns = "iaweapons" if "assets/iaweapons/models" in path.as_posix() else "_iainternal"

            parent = data.get("parent")
            if isinstance(parent, str) and not parent.startswith("minecraft:"):
                if ":" in parent:
                    ns, rel = parent.split(":", 1)
                else:
                    ns, rel = current_ns, parent
                if ns == "iaweapons":
                    target = root / "assets" / "iaweapons" / "models" / f"{rel}.json"
                elif ns == "_iainternal":
                    target = root / OVERLAY / "assets" / "_iainternal" / "models" / f"{rel}.json"
                else:
                    target = None
                if target is not None and not target.exists():
                    missing.append(f"model {parent} from {path}")

            textures = data.get("textures", {})
            if isinstance(textures, dict):
                for ref in textures.values():
                    if not isinstance(ref, str) or ref.startswith("#") or ref.startswith("minecraft:"):
                        continue
                    if ":" in ref:
                        ns, rel = ref.split(":", 1)
                    else:
                        ns, rel = current_ns, ref
                    if ns == "iaweapons":
                        target = root / "assets" / "iaweapons" / "textures" / f"{rel}.png"
                        if not target.exists():
                            missing.append(f"texture {ref} from {path}")

    if missing:
        raise ValueError("\n".join(missing))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source_zip", type=Path)
    parser.add_argument("output_zip", type=Path)
    args = parser.parse_args()
    build(args.source_zip, args.output_zip)
