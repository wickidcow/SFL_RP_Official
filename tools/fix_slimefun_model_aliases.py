from __future__ import annotations

import argparse
import json
import shutil
import tempfile
import zipfile
from pathlib import Path, PurePosixPath


MODEL_ROOT = "assets/slimefun/models/"
ATLAS_SUFFIX = "assets/minecraft/atlases/items.json"


def safe_member(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"unsafe ZIP member: {name}")
    return path


def extract_safe(zip_path: Path, destination: Path) -> None:
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            rel = safe_member(info.filename)
            if not rel.parts:
                continue
            target = destination.joinpath(*rel.parts)
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def collect_slimefun_sprite_aliases(root: Path) -> dict[str, str]:
    aliases: dict[str, str] = {}

    for atlas in root.rglob("items.json"):
        posix = atlas.relative_to(root).as_posix()
        if not posix.endswith(ATLAS_SUFFIX):
            continue

        data = load_json(atlas)
        for source in data.get("sources", []):
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
                raise ValueError(
                    f"conflicting Slimefun sprite aliases for {resource}: {previous} vs {sprite}"
                )
            aliases[resource] = sprite

    if not aliases:
        raise ValueError("no slimefun -> _slimefun sprite aliases were found in the pack")

    return aliases


def rewrite_texture_map(value, aliases: dict[str, str]) -> tuple[object, int]:
    changes = 0

    if isinstance(value, dict):
        rewritten = {}
        for key, child in value.items():
            if key == "textures" and isinstance(child, dict):
                textures = {}
                for texture_key, texture_value in child.items():
                    if isinstance(texture_value, str) and not texture_value.startswith("#"):
                        replacement = aliases.get(texture_value)
                        if replacement is not None and replacement != texture_value:
                            texture_value = replacement
                            changes += 1
                    else:
                        texture_value, nested = rewrite_texture_map(texture_value, aliases)
                        changes += nested
                    textures[texture_key] = texture_value
                rewritten[key] = textures
            else:
                rewritten_child, nested = rewrite_texture_map(child, aliases)
                rewritten[key] = rewritten_child
                changes += nested
        return rewritten, changes

    if isinstance(value, list):
        rewritten_list = []
        for child in value:
            rewritten_child, nested = rewrite_texture_map(child, aliases)
            rewritten_list.append(rewritten_child)
            changes += nested
        return rewritten_list, changes

    return value, 0


def patch_models(root: Path, aliases: dict[str, str]) -> tuple[list[str], int]:
    changed_files: list[str] = []
    changed_references = 0

    model_root = root / MODEL_ROOT
    if not model_root.is_dir():
        raise ValueError(f"missing {MODEL_ROOT}")

    for path in sorted(model_root.rglob("*.json")):
        original = load_json(path)
        rewritten, count = rewrite_texture_map(original, aliases)
        if count == 0:
            continue

        path.write_text(
            json.dumps(rewritten, ensure_ascii=False, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        changed_files.append(path.relative_to(root).as_posix())
        changed_references += count

    return changed_files, changed_references


def write_deterministic_zip(root: Path, output: Path) -> None:
    epoch = (2026, 1, 1, 0, 0, 0)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()

    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sorted(p for p in root.rglob("*") if p.is_file()):
            rel = path.relative_to(root).as_posix()
            info = zipfile.ZipInfo(rel, date_time=epoch)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            zf.writestr(
                info,
                path.read_bytes(),
                compress_type=zipfile.ZIP_DEFLATED,
                compresslevel=9,
            )


def fix_pack(source: Path, output: Path, report: Path | None = None) -> dict:
    with tempfile.TemporaryDirectory(prefix="sfl-alias-fix-") as temp:
        root = Path(temp) / "pack"
        root.mkdir()
        extract_safe(source, root)

        aliases = collect_slimefun_sprite_aliases(root)
        changed_files, changed_references = patch_models(root, aliases)

        result = {
            "source": source.name,
            "output": output.name,
            "sprite_aliases": len(aliases),
            "changed_models": len(changed_files),
            "changed_texture_references": changed_references,
            "changed_files": changed_files,
        }

        write_deterministic_zip(root, output)

    if report is not None:
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Repair standalone Slimefun model texture references that were normalized "
            "away from the _slimefun sprite aliases used by the modern item atlas."
        )
    )
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    result = fix_pack(args.source, args.output, args.report)
    print(
        "Slimefun sprite-alias repair complete: "
        f"{result['changed_models']} model(s), "
        f"{result['changed_texture_references']} texture reference(s), "
        f"{result['sprite_aliases']} known alias(es)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
