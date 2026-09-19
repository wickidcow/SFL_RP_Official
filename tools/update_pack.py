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


def deletion_entries(delete_list: Path | None) -> list[str]:
    if delete_list is None or not delete_list.exists():
        return []
    entries: list[str] = []
    for raw in delete_list.read_text(encoding="utf-8").splitlines():
        entry = raw.strip()
        if not entry or entry.startswith("#"):
            continue
        safe_member(entry)
        entries.append(entry)
    return entries


def override_files(overrides: Path | None) -> list[Path]:
    if overrides is None or not overrides.exists():
        return []
    return sorted(path for path in overrides.rglob("*") if path.is_file())


def apply_deletions(root: Path, entries: list[str]) -> None:
    for entry in entries:
        rel = safe_member(entry)
        target = root.joinpath(*rel.parts)
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()


def apply_overrides(root: Path, overrides: Path | None, files: list[Path]) -> None:
    if overrides is None:
        return
    for source in files:
        rel = source.relative_to(overrides)
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def write_deterministic_zip(root: Path, output: Path) -> None:
    # Fixed timestamps make identical changed input trees deterministic in CI.
    # A true no-op never reaches this function: the known-good ZIP is copied
    # byte-for-byte instead so its exact tested artifact hash is preserved.
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
            "over a known-good release. With no reviewed changes, the baseline "
            "ZIP is copied byte-for-byte."
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

    deletions = deletion_entries(args.delete_list)
    overrides = override_files(args.overrides)

    args.output.parent.mkdir(parents=True, exist_ok=True)

    # Critical regression guard: a no-op build must be the exact tested ZIP,
    # not merely a logically equivalent re-compressed archive.
    if not deletions and not overrides:
        if args.output.exists():
            args.output.unlink()
        shutil.copyfile(args.base, args.output)
        print(f"No reviewed changes: copied {args.base} byte-for-byte to {args.output}")
        return 0

    with tempfile.TemporaryDirectory(prefix="sfl-rp-") as temp:
        root = Path(temp) / "pack"
        root.mkdir()
        extract_safe(args.base, root)
        apply_deletions(root, deletions)
        apply_overrides(root, args.overrides, overrides)
        write_deterministic_zip(root, args.output)

    print(
        f"Built reviewed candidate with {len(overrides)} override file(s) "
        f"and {len(deletions)} deletion(s): {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
