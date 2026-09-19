from __future__ import annotations

import argparse
import json
import re
import shutil
import tempfile
import zipfile
from pathlib import Path

ALLOWED_NAMESPACES = {"minecraft", "slimefun", "pylon", "iaweapons", "_iainternal"}
CORE_EQUIPMENT = {"bee_wings.json", "infused_elytra.json", "slime_steel_armor.json", "soulbound_elytra.json"}

def extract(zip_path: Path, dest: Path):
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest)

def copy_tree(src: Path, dst: Path):
    if src.exists():
        shutil.copytree(src, dst, dirs_exist_ok=True)

def normalize_aliases(obj):
    replacements = {
        "_minecraft:": "minecraft:",
        "_b_minecraft:": "minecraft:",
        "_slimefun:": "slimefun:",
        "_b_slimefun:": "slimefun:",
        "_pylon:": "pylon:",
        "_b_pylon:": "pylon:",
        "_iaweapons:": "iaweapons:",
        "_b_iaweapons:": "iaweapons:",
    }
    if isinstance(obj, dict):
        return {key: normalize_aliases(value) for key, value in obj.items()}
    if isinstance(obj, list):
        return [normalize_aliases(value) for value in obj]
    if isinstance(obj, str):
        for old, new in replacements.items():
            if obj.startswith(old):
                return new + obj[len(old):]
    return obj

def refs(obj):
    found = []
    def walk(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in {"model", "texture", "resource", "base"} and isinstance(child, str):
                    found.append(child)
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    walk(obj)
    return found

def namespaces(obj):
    found = set()
    for ref in refs(obj):
        if ref.startswith("#") or ":" not in ref:
            continue
        ns = ref.split(":", 1)[0]
        if re.fullmatch(r"[a-z0-9_.-]+", ns):
            found.add(ns)
    return found

def asset_dirs(root: Path, namespace: str):
    result = []
    direct = root / "assets" / namespace
    if direct.exists():
        result.append(direct)
    for path in root.rglob(namespace):
        if path.is_dir() and path.parent.name == "assets" and path != direct:
            result.append(path)
    return sorted(dict.fromkeys(result), key=lambda p: (len(p.parts), p.as_posix()))

def item_dirs(root: Path):
    dirs = []
    direct = root / "assets" / "minecraft" / "items"
    if direct.exists():
        dirs.append(direct)
    for path in root.rglob("items"):
        if path.is_dir() and path.parent.name == "minecraft" and path.parent.parent.name == "assets" and path != direct:
            dirs.append(path)
    return sorted(dict.fromkeys(dirs), key=lambda p: (len(p.parts), p.as_posix()))

def load_item_candidates(root: Path):
    by_name = {}
    for directory in item_dirs(root):
        for path in directory.glob("*.json"):
            try:
                data = normalize_aliases(json.loads(path.read_text(encoding="utf-8")))
            except Exception:
                continue
            by_name.setdefault(path.stem, []).append((path, data))
    return by_name

def pick_fallback(candidates, item_name):
    # Prefer the root/current definition first, then the shallowest overlay.
    for path, data in candidates:
        model = data.get("model", {})
        if isinstance(model, dict) and model.get("fallback") is not None:
            return normalize_aliases(model["fallback"])
    return {"type": "minecraft:model", "model": f"minecraft:item/{item_name}"}

def build(slimefun_source: Path, pylon_source: Path, output_zip: Path):
    with tempfile.TemporaryDirectory(prefix="sfl-combined-") as temp:
        temp = Path(temp)
        sf = temp / "sf"
        py = temp / "pylon"
        out = temp / "pack"
        sf.mkdir(); py.mkdir(); out.mkdir()

        extract(slimefun_source, sf)
        extract(pylon_source, py)

        # Keep only the requested content namespaces.
        for src in asset_dirs(sf, "slimefun"):
            copy_tree(src, out / "assets" / "slimefun")
        for src in asset_dirs(py, "pylon"):
            copy_tree(src, out / "assets" / "pylon")
        for src in asset_dirs(sf, "iaweapons"):
            copy_tree(src, out / "assets" / "iaweapons")

        # IAWeapons firework launcher generated helper models.
        for internal in asset_dirs(sf, "_iainternal"):
            helper = internal / "models" / "item_context" / "iaweapons"
            if helper.exists():
                copy_tree(helper, out / "assets" / "_iainternal" / "models" / "item_context" / "iaweapons")

        # Slimefun custom equipment/player-visible armor assets.
        equipment_out = out / "assets" / "minecraft" / "equipment"
        textures_out = out / "assets" / "minecraft" / "textures" / "entity" / "equipment"
        for eqdir in sf.rglob("assets/minecraft/equipment"):
            for path in eqdir.glob("*.json"):
                if path.name in CORE_EQUIPMENT:
                    equipment_out.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, equipment_out / path.name)
        for texdir in sf.rglob("assets/minecraft/textures/entity/equipment"):
            if texdir.is_dir():
                copy_tree(texdir, textures_out)

        sf_items = load_item_candidates(sf)
        py_items = load_item_candidates(py)
        all_names = set(sf_items) | set(py_items)
        out_items = out / "assets" / "minecraft" / "items"
        out_items.mkdir(parents=True, exist_ok=True)

        stats = {"slimefun_numeric": 0, "iaweapons_numeric": 0, "pylon_string": 0, "item_files": 0}

        for name in sorted(all_names):
            sf_candidates = sf_items.get(name, [])
            py_candidates = py_items.get(name, [])
            fallback = pick_fallback(sf_candidates or py_candidates, name)

            numeric = []
            # Slimefun + IAWeapons both use numeric CustomModelData.
            for _, data in sf_candidates:
                model = data.get("model", {})
                if not isinstance(model, dict) or model.get("type") not in {"range_dispatch", "minecraft:range_dispatch"}:
                    continue
                for entry in model.get("entries", []):
                    entry = normalize_aliases(entry)
                    ns = namespaces(entry.get("model"))
                    if ns <= {"minecraft", "slimefun"} and "slimefun" in ns:
                        numeric.append(entry)
                        stats["slimefun_numeric"] += 1
                    elif ns <= {"minecraft", "iaweapons", "_iainternal"} and ("iaweapons" in ns or "_iainternal" in ns):
                        numeric.append(entry)
                        stats["iaweapons_numeric"] += 1

            # Some source packs keep IAWeapons in a separate overlay using range dispatch.
            # The scan above finds those overlays automatically.
            by_threshold = {}
            for entry in numeric:
                threshold = entry.get("threshold")
                if threshold in by_threshold and by_threshold[threshold] != entry:
                    raise ValueError(f"Numeric CustomModelData collision for {name}: {threshold}")
                by_threshold[threshold] = entry
            numeric = [by_threshold[key] for key in sorted(by_threshold, key=lambda v: float(v))]

            merged = fallback
            if numeric:
                merged = {
                    "type": "minecraft:range_dispatch",
                    "property": "minecraft:custom_model_data",
                    "index": 0,
                    "fallback": fallback,
                    "entries": numeric,
                }

            # Pylon uses string CustomModelData. Nest its select around numeric dispatch
            # so both systems work on the same vanilla carrier item.
            cases = []
            for _, data in py_candidates:
                model = data.get("model", {})
                if not isinstance(model, dict) or model.get("type") not in {"select", "minecraft:select"}:
                    continue
                for case in model.get("cases", []):
                    case = normalize_aliases(case)
                    when = case.get("when")
                    ns = namespaces(case.get("model"))
                    if isinstance(when, str) and when.startswith("pylon:") and ns <= {"minecraft", "pylon"}:
                        cases.append(case)

            # Deduplicate Pylon case keys.
            by_when = {}
            for case in cases:
                when = case["when"]
                if when in by_when and by_when[when] != case:
                    raise ValueError(f"Pylon CustomModelData collision for {name}: {when}")
                by_when[when] = case
            cases = [by_when[key] for key in sorted(by_when)]
            stats["pylon_string"] += len(cases)

            if cases:
                merged = {
                    "type": "minecraft:select",
                    "property": "minecraft:custom_model_data",
                    "index": 0,
                    "cases": cases,
                    "fallback": merged,
                }

            if numeric or cases:
                (out_items / f"{name}.json").write_text(
                    json.dumps({"model": merged}, indent=2) + "\n",
                    encoding="utf-8",
                )
                stats["item_files"] += 1

        # Preserve vanilla sprites while adding only Pylon and IAWeapons explicit atlas entries.
        atlas_out = out / "assets" / "minecraft" / "atlases"
        atlas_out.mkdir(parents=True, exist_ok=True)
        for atlas_name, default_dir in (("items.json", "item"), ("blocks.json", "block")):
            sources = [{"type": "minecraft:directory", "source": default_dir, "prefix": default_dir + "/"}]

            for atlas in py.rglob(f"assets/minecraft/atlases/{atlas_name}"):
                data = json.loads(atlas.read_text(encoding="utf-8"))
                for source in data.get("sources", []):
                    resource = source.get("resource", "") if isinstance(source, dict) else ""
                    if isinstance(resource, str) and resource.startswith("pylon:"):
                        sources.append(normalize_aliases(source))

            if atlas_name == "items.json":
                for atlas in sf.rglob("assets/minecraft/atlases/items.json"):
                    data = json.loads(atlas.read_text(encoding="utf-8"))
                    for source in data.get("sources", []):
                        resource = source.get("resource", "") if isinstance(source, dict) else ""
                        if isinstance(resource, str) and resource.startswith("iaweapons:"):
                            sources.append(normalize_aliases(source))

            unique = []
            seen = set()
            for source in sources:
                marker = json.dumps(source, sort_keys=True)
                if marker not in seen:
                    seen.add(marker)
                    unique.append(source)
            (atlas_out / atlas_name).write_text(json.dumps({"sources": unique}, indent=2) + "\n", encoding="utf-8")

        # Normalize retained private aliases.
        for path in out.rglob("*.json"):
            data = normalize_aliases(json.loads(path.read_text(encoding="utf-8")))
            path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

        # Use the approved purple Slimefun icon from the source release.
        icon = sf / "pack.png"
        if icon.exists():
            shutil.copy2(icon, out / "pack.png")

        meta = {
            "pack": {
                "pack_format": 75,
                "min_format": 75,
                "max_format": 9999,
                "description": "Slimefun Legacy + Pylon + IAWeapons • Minecraft 1.21.11+",
            }
        }
        (out / "pack.mcmeta").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
        (out / "README.txt").write_text(
            "Slimefun Legacy + Pylon + IAWeapons Resource Pack\n"
            "Minecraft Java 1.21.11+; validated through 26.3.\n"
            "Only Slimefun core, Pylon, IAWeapons, and required Minecraft/helper assets are retained.\n"
            "Player-head/skull special-model fallbacks are preserved.\n",
            encoding="utf-8",
        )

        validate(out, stats)

        if output_zip.exists():
            output_zip.unlink()
        with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
            for path in sorted(out.rglob("*")):
                if path.is_file():
                    zf.write(path, path.relative_to(out).as_posix())

        print(json.dumps(stats, sort_keys=True))

def validate(root: Path, stats):
    bad = []
    for path in root.rglob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            bad.append(f"Invalid JSON {path}: {exc}")
            continue
        for ref in refs(data):
            if ref.startswith("#") or ":" not in ref:
                continue
            ns = ref.split(":", 1)[0]
            if re.fullmatch(r"[a-z0-9_.-]+", ns) and ns not in ALLOWED_NAMESPACES:
                bad.append(f"Removed namespace {ns}: {path} -> {ref}")

    head = root / "assets" / "minecraft" / "items" / "player_head.json"
    if not head.exists():
        bad.append("player_head.json missing")
    else:
        text = head.read_text(encoding="utf-8")
        if "minecraft:head" not in text or '"kind": "player"' not in text:
            bad.append("player-head special fallback was not preserved")

    top_namespaces = {p.name for p in (root / "assets").iterdir() if p.is_dir()}
    extra = top_namespaces - ALLOWED_NAMESPACES
    if extra:
        bad.append(f"Unexpected asset namespaces: {sorted(extra)}")

    if stats["slimefun_numeric"] == 0:
        bad.append("No Slimefun mappings retained")
    if stats["pylon_string"] == 0:
        bad.append("No Pylon mappings retained")
    if stats["iaweapons_numeric"] == 0:
        bad.append("No IAWeapons mappings retained")

    if bad:
        raise ValueError("\n".join(bad))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("slimefun_source", type=Path)
    parser.add_argument("pylon_source", type=Path)
    parser.add_argument("output_zip", type=Path)
    args = parser.parse_args()
    build(args.slimefun_source, args.pylon_source, args.output_zip)
