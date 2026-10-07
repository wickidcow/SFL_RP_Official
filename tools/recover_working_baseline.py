from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
import zipfile
from pathlib import Path, PurePosixPath


ITEM_SUFFIX = "assets/minecraft/items/"
EXPECTED_PREVIEW_SHA256 = "90d20e4693731a2865fd2238d5daf8afb453fbd85e592a07e7d453728bc71bd3"
EXPECTED_CHANGED_DEFINITIONS = 295

WORKING_CANONICAL_HASHES = {
    "wooden_hoe": "bfcc45f5695719851f8e1fecde1de34ae224ddf23c3faefdeda25eb880fe7405",
    "leather_helmet": "034059c6b4774bfad32ba97770b55ec2791c34f6267076282c302d6ee4b6aa3c",
    "leather_chestplate": "36dd7f46f3c4c5d96226fc6617a5e02dbedcf88cb9e1904b3c0152b6ad7a7f97",
    "leather_leggings": "d6c7e7809544ae0e38d2ac246f7e32d1d0b357244548144517e702e3337c0b85",
    "leather_boots": "60154970567cc840f751b37e20a7ca9326d2a17a2fe967555ac1fe488bc038db",
    "chainmail_helmet": "11f438f2c5580e84a44a9708fb48cdab4d08d7de6aaac0448a26c05c82560dbd",
    "chainmail_chestplate": "35481d4896f4ffb0679b99b71f72877ff26591651d69ac2db2118dca5afc9f16",
    "chainmail_leggings": "ecbb1ec93999c908897819fd5964456d8cf893de6471b822aa841e26102060aa",
    "chainmail_boots": "7506442a7a516ee83b95ec7057ff032c09d23b0d41fb2dca406985889561622a",
    "iron_helmet": "12091578f3ce329e3f96ae16cf9789d2bd4881756d03f4a48245df84f13e159f",
    "iron_chestplate": "41b84abd369f95f5130219c9f70bc9ff264ccd95976a26d42670d00f47b3682d",
    "iron_leggings": "fa7ffa8397bb0a97fcfc31905e4c91144b364941f0d1005de5fdeb0e5c670dcb",
    "iron_boots": "cf4ed8ffc4813c035ee989d36a23c43ca542732fdda3784b378b251c94e568eb",
    "golden_helmet": "b9fed125d755dda3af231c04f54d96e24df04be75dbe2a2c9b1cbdc6b2268feb",
    "golden_chestplate": "3e93da542da00eb467ec39e5d0c3b4ab6581d97e2b94b893da7c97e8c92bd6c2",
    "golden_leggings": "416a8ff1e4d6db578c30fd717ccf862c1edaea967333940f83c1c7e006d2d678",
    "golden_boots": "a6045ef80e5543ab5d1f3fce67fccebc17dfdd4cfaa468ab473904769119070b",
    "diamond_helmet": "cc00d7fa13bd0152300df88934ec6744291d2828d3999618bac112f584664cf1",
    "diamond_chestplate": "146c09ecb8b5b10dc9a76297feb7911250ef1b33dc8404a58315901704bf33d5",
    "diamond_leggings": "4fc479ea6851283c295b239898677560dba80f3466f5774aea6550ea273ea60a",
    "diamond_boots": "06a2ba5e6963820dbf730a6ff5e7261fbb6bed9661b76c8590de6dd0766d87bf",
    "netherite_helmet": "bb3f588be3a9e61723976ae1ae2d46af24f4bd1857a3233deab7bd8248fe5f53",
    "netherite_chestplate": "12f8b3e162e2002b4e72daf26ff53c462ae3ef01dc1d8e6502be13749fc36cbf",
    "netherite_leggings": "0867d8fa357cf4df08acab694f6f9616ef7472c689bbf08a7b5b28f1ae67f359",
    "netherite_boots": "7e38e806a0c73d990559f216d98f1851c395dc67c0d37cb81638258e9b039908",
    "chest": "6ff2b5e74b8f48e3cb4004ad21efe81e0702ea3f428952a5122b1904991ce09a",
    "compass": "046d13cf9974feace0a653e1e4b2c88c116d09a5314205c62c008e2d223b075d",
    "clock": "2d0730b07250fc378d5c73962ffbb47b42fcb84daeb646d5c675681a05655c8f",
    "trident": "6e5d10ede46cc679a8f06f2cc5d1e02234ca252e3a5c90f02923ae8b07aabef2",
    "crossbow": "0ef4c367408e9f43640d9ddf579b4d942734edf61bfc5b3f590ca65b6de17a44",
    "oak_planks": "7873bd6583edb6a17615f5492b8f01b836cdff7b8978ae1198f248fc107f4eaf",
}


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


def is_identity_wrapper(model: object) -> bool:
    if not isinstance(model, dict):
        return False
    type_name = str(model.get("type", "")).removeprefix("minecraft:")
    prop = str(model.get("property", "")).removeprefix("minecraft:")
    component = str(model.get("component", "")).removeprefix("minecraft:")
    if type_name != "condition" or prop != "has_component" or component != "custom_model_data":
        return False
    if not isinstance(model.get("on_true"), dict) or not isinstance(model.get("on_false"), dict):
        return False

    node = model["on_false"]
    while isinstance(node, dict):
        node_type = str(node.get("type", "")).removeprefix("minecraft:")
        node_prop = str(node.get("property", "")).removeprefix("minecraft:")
        if node_type != "condition":
            return False
        if node_prop == "component" and node.get("predicate") == "minecraft:custom_data":
            value = node.get("value")
            if isinstance(value, dict) and isinstance(value.get("PublicBukkitValues"), dict):
                return True
        node = node.get("on_false")
    return False


def canonical_hash(document: dict) -> str:
    payload = json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def recover_tree(root: Path) -> dict:
    changed = []
    for path in sorted(root.rglob("assets/minecraft/items/*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        model = document.get("model")
        if not is_identity_wrapper(model):
            continue
        document["model"] = model["on_true"]
        path.write_text(
            json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        changed.append(path.relative_to(root).as_posix())

    if len(changed) != EXPECTED_CHANGED_DEFINITIONS:
        raise ValueError(
            f"identity preview changed {len(changed)} item definitions; "
            f"expected {EXPECTED_CHANGED_DEFINITIONS}"
        )

    mismatches = {}
    for item, expected in WORKING_CANONICAL_HASHES.items():
        path = root / f"assets/minecraft/items/{item}.json"
        if not path.is_file():
            mismatches[item] = {"expected": expected, "actual": None}
            continue
        actual = canonical_hash(json.loads(path.read_text(encoding="utf-8")))
        if actual != expected:
            mismatches[item] = {"expected": expected, "actual": actual}

    if mismatches:
        raise ValueError(f"recovered carrier definitions do not match working pack: {mismatches}")

    meta = json.loads((root / "pack.mcmeta").read_text(encoding="utf-8"))
    overlays = meta.get("overlays", {}).get("entries", [])
    if overlays != [{"directory": "sfl_26_1_plus", "min_format": 84, "max_format": 9999}]:
        raise ValueError(f"unexpected recovered overlay layout: {overlays!r}")

    return {"changed_files": changed, "carrier_hashes": WORKING_CANONICAL_HASHES}


def write_deterministic_zip(root: Path, output: Path) -> None:
    epoch = (2026, 1, 1, 0, 0, 0)
    if output.exists():
        output.unlink()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sorted(p for p in root.rglob("*") if p.is_file()):
            rel = path.relative_to(root).as_posix()
            info = zipfile.ZipInfo(rel, date_time=epoch)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            zf.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def recover_pack(source: Path, output: Path, report_path: Path | None = None) -> dict:
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    if source_hash != EXPECTED_PREVIEW_SHA256:
        raise ValueError(
            f"preview SHA-256 mismatch: expected {EXPECTED_PREVIEW_SHA256}, got {source_hash}"
        )

    with tempfile.TemporaryDirectory(prefix="sfl-working-recovery-") as temp:
        root = Path(temp) / "pack"
        root.mkdir()
        extract_safe(source, root)
        report = recover_tree(root)
        write_deterministic_zip(root, output)

    report["source_sha256"] = source_hash
    report["output_sha256"] = hashlib.sha256(output.read_bytes()).hexdigest()

    if report_path is not None:
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Recover the owner-confirmed working v4 resource-pack structure from "
            "the reviewed v4.1 identity preview by removing only its 295 client-side "
            "identity wrappers."
        )
    )
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = recover_pack(args.source, args.output, args.report)
    print(
        f"Recovered working RP structure: {len(report['changed_files'])} identity wrappers removed; "
        f"SHA-256 {report['output_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
