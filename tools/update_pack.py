from __future__ import annotations

import argparse
import shutil
import tempfile
import zipfile
from pathlib import Path, PurePosixPath


def safe_member(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"unsafe ZIP member: {name}")
    return path


def extract_safe(zip_path: Path, destination: Path) -> None:
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            path = safe_member(info.filename)
            if not path.parts:
                continue
            target = destination.joinpath(*path.parts)
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)


def apply_deletions(root: Path, delete_list: Path | None) -> None:
    if delete_list is None or not delete_list.exists():
        return
    for raw in delete_list.read_text(encoding="utf-8").splitlines():
        entry = raw.strip()
        if not entry or entry.startswith("#"):
            continue
        rel = safe_member(entry)
        target = root.joinpath(*rel.parts)
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()


def apply_overrides(root: Path, overrides: Path | None) -> None:
    if overrides is None or not overrides.exists():
        return
    for source in sorted(overrides.rglob("*")):
        if not source.is_file():
            continue
        rel = source.relative_to(overrides)
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def write_deterministic_zip(root: Path, output: Path) -> None:
    # Fixed timestamps make identical input trees produce identical ZIP bytes in CI.
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


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build a future SlimefunLegacyRP.zip by layering reviewed changes "
            "over a known-good release."
        )
    )
    parser.add_argument("base", type=Path, help="Known-good SlimefunLegacyRP.zip")
    parser.add_argument("output", type=Path, help="Output SlimefunLegacyRP.zip")
    parser.add_argument(
        "--overrides",
        type=Path,
        default=Path("overrides"),
        help="Files copied over the base pack",
    )
    parser.add_argument(
        "--delete-list",
        type=Path,
        default=Path("deletions.txt"),
        help="Pack-relative paths to remove",
    )
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="sfl-rp-") as temp:
        root = Path(temp) / "pack"
        root.mkdir()
        extract_safe(args.base, root)
        apply_deletions(root, args.delete_list)
        apply_overrides(root, args.overrides)
        write_deterministic_zip(root, args.output)

    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
