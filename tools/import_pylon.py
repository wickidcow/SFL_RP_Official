from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import zipfile
from pathlib import Path, PurePosixPath

TRACKED_NAMESPACES = ("pylon", "rebar", "rebarmobs")
ITEM_DEFS = "assets/minecraft/items/"
ATLAS_FILES = (
    "assets/minecraft/atlases/items.json",
    "assets/minecraft/atlases/blocks.json",
)


def read_zip(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as zf:
        bad = zf.testzip()
        if bad:
            raise ValueError(f"{path} has CRC failure at {bad}")
        return {n: zf.read(n) for n in zf.namelist() if not n.endswith("/")}


def json_load(files: dict[str, bytes], name: str):
    raw = files.get(name)
    if raw is None:
        return None
    return json.loads(raw)


def json_bytes(data) -> bytes:
    return (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def is_tracked_namespace_file(name: str) -> bool:
    return any(name.startswith(f"assets/{ns}/") for ns in TRACKED_NAMESPACES)


def is_cmd0_select(node) -> bool:
    return (
        isinstance(node, dict)
        and node.get("type") in {"select", "minecraft:select"}
        and node.get("property") in {"custom_model_data", "minecraft:custom_model_data"}
        and int(node.get("index", 0)) == 0
        and isinstance(node.get("cases"), list)
    )


def pylon_cases(data) -> dict[str, dict]:
    if not isinstance(data, dict):
        return {}
    root = data.get("model")
    if not is_cmd0_select(root):
        return {}
    out: dict[str, dict] = {}
    for case in root.get("cases", []):
        when = case.get("when") if isinstance(case, dict) else None
        if isinstance(when, str) and when.startswith("pylon:"):
            out[when] = case
    return out


def find_or_wrap_cmd0_select(data: dict, item_name: str) -> dict:
    root = data.get("model")
    if is_cmd0_select(root):
        return root

    fallback = root if isinstance(root, dict) else {
        "type": "minecraft:model",
        "model": f"minecraft:item/{item_name}",
    }
    wrapped = {
        "type": "minecraft:select",
        "property": "custom_model_data",
        "index": 0,
        "cases": [],
        "fallback": fallback,
    }
    data["model"] = wrapped
    return wrapped


def case_index(select_node: dict) -> dict[str, int]:
    result: dict[str, int] = {}
    for idx, case in enumerate(select_node.get("cases", [])):
        when = case.get("when") if isinstance(case, dict) else None
        if isinstance(when, str):
            result[when] = idx
    return result


def tracked_atlas_sources(atlas) -> dict[str, dict]:
    result: dict[str, dict] = {}
    if not isinstance(atlas, dict):
        return result
    for source in atlas.get("sources", []):
        if not isinstance(source, dict):
            continue
        blob = canonical(source)
        if any(f"{ns}:" in blob for ns in TRACKED_NAMESPACES):
            result[blob] = source
    return result


def write_zip_from_files(files: dict[str, bytes], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()

    epoch = (2026, 1, 1, 0, 0, 0)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for name in sorted(files):
            info = zipfile.ZipInfo(name, date_time=epoch)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            zf.writestr(
                info,
                files[name],
                compress_type=zipfile.ZIP_DEFLATED,
                compresslevel=9,
            )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Safely import upstream Pylon resource-pack changes into a "
            "known-good Slimefun Legacy resource pack."
        )
    )
    parser.add_argument("baseline", type=Path)
    parser.add_argument("old_pylon", type=Path)
    parser.add_argument("new_pylon", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--old-ref", default="")
    parser.add_argument("--new-ref", default="")
    args = parser.parse_args()

    baseline = read_zip(args.baseline)
    old = read_zip(args.old_pylon)
    new = read_zip(args.new_pylon)

    report = {
        "old_ref": args.old_ref,
        "new_ref": args.new_ref,
        "namespace_added": [],
        "namespace_updated": [],
        "namespace_conflicts": [],
        "namespace_deletions_for_review": [],
        "carrier_added": [],
        "carrier_updated": [],
        "carrier_conflicts": [],
        "carrier_deletions_for_review": [],
        "atlas_added": [],
        "atlas_deletions_for_review": [],
    }

    # If upstream generated bytes are unchanged, preserve the exact tested ZIP.
    if old == new:
        shutil.copyfile(args.baseline, args.output)
        metadata = {
            **report,
            "changed": False,
            "conflict_count": 0,
            "deletion_review_count": 0,
        }
        args.metadata.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
        args.report.write_text(
            "# Pylon update report\n\n"
            "No upstream Pylon resource-pack changes were detected. "
            "The candidate is byte-for-byte identical to the confirmed SFL baseline.\n",
            encoding="utf-8",
        )
        print("No upstream Pylon changes; copied baseline byte-for-byte.")
        return 0

    out = dict(baseline)

    # 1) Namespace assets.
    # Only apply files that actually changed between the accepted and new Pylon refs.
    old_ns = {n: b for n, b in old.items() if is_tracked_namespace_file(n)}
    new_ns = {n: b for n, b in new.items() if is_tracked_namespace_file(n)}

    for name in sorted(set(old_ns) | set(new_ns)):
        old_b = old_ns.get(name)
        new_b = new_ns.get(name)
        base_b = baseline.get(name)

        if old_b is None and new_b is not None:
            if base_b is None or base_b == new_b:
                out[name] = new_b
                report["namespace_added"].append(name)
            else:
                report["namespace_conflicts"].append(
                    {
                        "path": name,
                        "reason": "new upstream file collides with an existing local file",
                    }
                )
        elif old_b is not None and new_b is None:
            if base_b == old_b:
                report["namespace_deletions_for_review"].append(name)
            elif base_b is not None:
                report["namespace_conflicts"].append(
                    {
                        "path": name,
                        "reason": "upstream deleted a locally modified file",
                    }
                )
        elif old_b != new_b:
            if base_b == old_b or base_b == new_b:
                out[name] = new_b
                report["namespace_updated"].append(name)
            else:
                report["namespace_conflicts"].append(
                    {
                        "path": name,
                        "reason": "local file differs from accepted upstream version",
                    }
                )

    # 2) Carrier item definitions.
    # Never replace a combined minecraft/items file. Merge only Pylon's top-level
    # string CustomModelData cases into the existing SFL carrier definition.
    old_item_names = {
        n for n in old if n.startswith(ITEM_DEFS) and n.endswith(".json")
    }
    new_item_names = {
        n for n in new if n.startswith(ITEM_DEFS) and n.endswith(".json")
    }

    for name in sorted(old_item_names | new_item_names):
        old_data = json_load(old, name) or {}
        new_data = json_load(new, name) or {}
        old_cases = pylon_cases(old_data)
        new_cases = pylon_cases(new_data)
        if old_cases == new_cases:
            continue

        item_name = PurePosixPath(name).stem
        base_data = json_load(out, name)
        if base_data is None:
            base_data = {
                "model": {
                    "type": "minecraft:model",
                    "model": f"minecraft:item/{item_name}",
                }
            }

        select_node = find_or_wrap_cmd0_select(base_data, item_name)
        idx_by_when = case_index(select_node)

        for when in sorted(set(old_cases) | set(new_cases)):
            old_case = old_cases.get(when)
            new_case = new_cases.get(when)
            idx = idx_by_when.get(when)
            base_case = select_node["cases"][idx] if idx is not None else None

            if old_case is None and new_case is not None:
                if base_case is None:
                    select_node["cases"].append(new_case)
                    idx_by_when[when] = len(select_node["cases"]) - 1
                    report["carrier_added"].append(
                        {"carrier": item_name, "when": when}
                    )
                elif canonical(base_case) != canonical(new_case):
                    report["carrier_conflicts"].append(
                        {
                            "carrier": item_name,
                            "when": when,
                            "reason": (
                                "new upstream Pylon case collides with an "
                                "existing local case"
                            ),
                        }
                    )
            elif old_case is not None and new_case is None:
                if base_case is not None and canonical(base_case) == canonical(old_case):
                    report["carrier_deletions_for_review"].append(
                        {"carrier": item_name, "when": when}
                    )
                elif base_case is not None:
                    report["carrier_conflicts"].append(
                        {
                            "carrier": item_name,
                            "when": when,
                            "reason": "upstream removed a locally modified Pylon case",
                        }
                    )
            elif canonical(old_case) != canonical(new_case):
                if base_case is None:
                    report["carrier_conflicts"].append(
                        {
                            "carrier": item_name,
                            "when": when,
                            "reason": "changed upstream Pylon case is missing locally",
                        }
                    )
                elif canonical(base_case) in {
                    canonical(old_case),
                    canonical(new_case),
                }:
                    select_node["cases"][idx] = new_case
                    report["carrier_updated"].append(
                        {"carrier": item_name, "when": when}
                    )
                else:
                    report["carrier_conflicts"].append(
                        {
                            "carrier": item_name,
                            "when": when,
                            "reason": (
                                "local Pylon case differs from accepted "
                                "upstream version"
                            ),
                        }
                    )

        # Keep non-Pylon cases untouched. Sort only Pylon cases for stable output.
        pylon_only = [
            c
            for c in select_node["cases"]
            if isinstance(c, dict)
            and isinstance(c.get("when"), str)
            and c["when"].startswith("pylon:")
        ]
        other = [
            c
            for c in select_node["cases"]
            if not (
                isinstance(c, dict)
                and isinstance(c.get("when"), str)
                and c["when"].startswith("pylon:")
            )
        ]
        pylon_only.sort(key=lambda c: c["when"])
        select_node["cases"] = pylon_only + other
        out[name] = json_bytes(base_data)

    # 3) Atlases.
    # Add new Pylon/Rebar/RebarMobs registrations only. Never delete upstream
    # atlas entries automatically.
    for atlas_name in ATLAS_FILES:
        old_atlas = json_load(old, atlas_name) or {"sources": []}
        new_atlas = json_load(new, atlas_name) or {"sources": []}
        old_sources = tracked_atlas_sources(old_atlas)
        new_sources = tracked_atlas_sources(new_atlas)
        base_atlas = json_load(out, atlas_name)
        if base_atlas is None:
            raise ValueError(f"baseline missing required atlas {atlas_name}")

        base_sources = base_atlas.setdefault("sources", [])
        base_keys = {
            canonical(source)
            for source in base_sources
            if isinstance(source, dict)
        }

        for key in sorted(set(new_sources) - set(old_sources)):
            source = new_sources[key]
            if key not in base_keys:
                base_sources.append(source)
                base_keys.add(key)
                report["atlas_added"].append(
                    {"atlas": atlas_name, "source": source}
                )

        for key in sorted(set(old_sources) - set(new_sources)):
            report["atlas_deletions_for_review"].append(
                {"atlas": atlas_name, "source": old_sources[key]}
            )

        out[atlas_name] = json_bytes(base_atlas)

    if out == baseline:
        shutil.copyfile(args.baseline, args.output)
    else:
        write_zip_from_files(out, args.output)

    conflict_count = (
        len(report["namespace_conflicts"]) + len(report["carrier_conflicts"])
    )
    deletion_review_count = (
        len(report["namespace_deletions_for_review"])
        + len(report["carrier_deletions_for_review"])
        + len(report["atlas_deletions_for_review"])
    )

    metadata = {
        **report,
        "changed": out != baseline,
        "conflict_count": conflict_count,
        "deletion_review_count": deletion_review_count,
    }
    args.metadata.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Pylon update report",
        "",
        f"- Accepted upstream ref: {args.old_ref or 'unknown'}",
        f"- Candidate upstream ref: {args.new_ref or 'unknown'}",
        f"- Candidate differs from SFL baseline: {'yes' if out != baseline else 'no'}",
        f"- Conflicts requiring review: {conflict_count}",
        f"- Upstream deletions requiring review: {deletion_review_count}",
        "",
        "## Imported changes",
        "",
        f"- Namespace files added: {len(report['namespace_added'])}",
        f"- Namespace files updated: {len(report['namespace_updated'])}",
        f"- Carrier cases added: {len(report['carrier_added'])}",
        f"- Carrier cases updated: {len(report['carrier_updated'])}",
        f"- Atlas sources added: {len(report['atlas_added'])}",
        "",
        (
            "Upstream deletions are never applied automatically. "
            "Local conflicts are preserved and reported."
        ),
    ]

    if report["namespace_conflicts"] or report["carrier_conflicts"]:
        lines.extend(["", "## Conflicts", ""])
        for item in report["namespace_conflicts"]:
            lines.append(f"- {item['path']} — {item['reason']}")
        for item in report["carrier_conflicts"]:
            lines.append(
                f"- {item['carrier']} / {item['when']} — {item['reason']}"
            )

    if deletion_review_count:
        lines.extend(["", "## Deletions requiring review", ""])
        for item in report["namespace_deletions_for_review"]:
            lines.append(f"- Namespace file: {item}")
        for item in report["carrier_deletions_for_review"]:
            lines.append(
                f"- Carrier case: {item['carrier']} / {item['when']}"
            )
        for item in report["atlas_deletions_for_review"]:
            lines.append(
                f"- Atlas source in {item['atlas']}: {canonical(item['source'])}"
            )

    args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(
        f"Pylon candidate built. changed={out != baseline} "
        f"conflicts={conflict_count} "
        f"deletions_for_review={deletion_review_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
