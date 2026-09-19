from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


SCRIPT = Path(__file__).with_name("import_pylon.py")


def j(value) -> bytes:
    return (json.dumps(value, indent=2) + "\n").encode()


def write_zip(path: Path, files: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            zf.writestr(name, data)


def read_zip(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as zf:
        return {n: zf.read(n) for n in zf.namelist() if not n.endswith("/")}


def item(cases: list[dict], fallback: str = "minecraft:item/apple") -> bytes:
    return j(
        {
            "model": {
                "type": "minecraft:select",
                "property": "custom_model_data",
                "index": 0,
                "cases": cases,
                "fallback": {"type": "minecraft:model", "model": fallback},
            }
        }
    )


def case(when: str, model: str) -> dict:
    return {
        "when": when,
        "model": {"type": "minecraft:model", "model": model},
    }


class PylonImporterTests(unittest.TestCase):
    def run_import(
        self,
        baseline_files: dict[str, bytes],
        old_files: dict[str, bytes],
        new_files: dict[str, bytes],
    ):
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        baseline = root / "baseline.zip"
        old = root / "old.zip"
        new = root / "new.zip"
        output = root / "out.zip"
        report = root / "report.md"
        metadata = root / "metadata.json"

        write_zip(baseline, baseline_files)
        write_zip(old, old_files)
        write_zip(new, new_files)

        subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                str(baseline),
                str(old),
                str(new),
                str(output),
                "--report",
                str(report),
                "--metadata",
                str(metadata),
                "--old-ref",
                "old",
                "--new-ref",
                "new",
            ],
            check=True,
        )

        return temp, baseline, output, json.loads(metadata.read_text()), report

    def base_files(self) -> dict[str, bytes]:
        return {
            "pack.mcmeta": j({"pack": {"pack_format": 75}}),
            "assets/minecraft/items/apple.json": item(
                [
                    case("pylon:old_item", "pylon:item/old"),
                    case("other:keep_me", "other:item/keep"),
                ]
            ),
            "assets/minecraft/items/comparator.json": item(
                [case("rebar:old", "rebar:item/old")],
                "minecraft:item/comparator",
            ),
            "assets/minecraft/items/black_concrete.json": item(
                [case("fluid_pipe_display:pylon:old", "pylon:block/old")],
                "minecraft:item/black_concrete",
            ),
            "assets/minecraft/atlases/items.json": j(
                {"sources": [{"type": "single", "resource": "pylon:item/old"}]}
            ),
            "assets/minecraft/atlases/blocks.json": j(
                {"sources": [{"type": "single", "resource": "pylon:block/old"}]}
            ),
            "assets/pylon/models/item/old.json": b"old-model",
            "assets/rebar/models/item/old.json": b"old-rebar",
        }

    def upstream_old(self) -> dict[str, bytes]:
        return {
            "assets/minecraft/items/apple.json": item(
                [case("pylon:old_item", "pylon:item/old")]
            ),
            "assets/minecraft/items/comparator.json": item(
                [case("rebar:old", "rebar:item/old")],
                "minecraft:item/comparator",
            ),
            "assets/minecraft/items/black_concrete.json": item(
                [case("fluid_pipe_display:pylon:old", "pylon:block/old")],
                "minecraft:item/black_concrete",
            ),
            "assets/minecraft/atlases/items.json": j(
                {"sources": [{"type": "single", "resource": "pylon:item/old"}]}
            ),
            "assets/minecraft/atlases/blocks.json": j(
                {"sources": [{"type": "single", "resource": "pylon:block/old"}]}
            ),
            "assets/pylon/models/item/old.json": b"old-model",
            "assets/rebar/models/item/old.json": b"old-rebar",
        }

    def test_no_change_is_byte_for_byte_copy(self):
        baseline_files = self.base_files()
        upstream = self.upstream_old()
        temp, baseline, output, metadata, _ = self.run_import(
            baseline_files, upstream, upstream
        )
        try:
            self.assertEqual(baseline.read_bytes(), output.read_bytes())
            self.assertFalse(metadata["changed"])
            self.assertEqual(metadata["conflict_count"], 0)
        finally:
            temp.cleanup()

    def test_adds_and_updates_all_upstream_carrier_namespaces(self):
        baseline_files = self.base_files()
        old = self.upstream_old()
        new = dict(old)

        new["assets/pylon/models/item/new.json"] = b"new-model"
        new["assets/rebarmobs/models/item/new.json"] = b"new-rebarmobs"

        new["assets/minecraft/items/apple.json"] = item(
            [
                case("pylon:old_item", "pylon:item/updated"),
                case("pylon:new_item", "pylon:item/new"),
            ]
        )
        new["assets/minecraft/items/comparator.json"] = item(
            [
                case("rebar:old", "rebar:item/old"),
                case("rebar:new", "rebar:item/new"),
            ],
            "minecraft:item/comparator",
        )
        new["assets/minecraft/items/black_concrete.json"] = item(
            [
                case("fluid_pipe_display:pylon:old", "pylon:block/old"),
                case("fluid_pipe_display:pylon:new", "pylon:block/new"),
            ],
            "minecraft:item/black_concrete",
        )
        new["assets/minecraft/atlases/items.json"] = j(
            {
                "sources": [
                    {"type": "single", "resource": "pylon:item/old"},
                    {"type": "single", "resource": "pylon:item/new"},
                    {"type": "single", "resource": "rebarmobs:item/new"},
                ]
            }
        )

        temp, _, output, metadata, _ = self.run_import(
            baseline_files, old, new
        )
        try:
            files = read_zip(output)
            self.assertEqual(files["assets/pylon/models/item/new.json"], b"new-model")
            self.assertEqual(
                files["assets/rebarmobs/models/item/new.json"], b"new-rebarmobs"
            )

            apple = json.loads(files["assets/minecraft/items/apple.json"])
            cases = {
                c["when"]: c
                for c in apple["model"]["cases"]
            }
            self.assertEqual(
                cases["pylon:old_item"]["model"]["model"],
                "pylon:item/updated",
            )
            self.assertIn("pylon:new_item", cases)
            self.assertIn("other:keep_me", cases)

            comparator = json.loads(
                files["assets/minecraft/items/comparator.json"]
            )
            self.assertIn(
                "rebar:new",
                {c["when"] for c in comparator["model"]["cases"]},
            )

            black = json.loads(
                files["assets/minecraft/items/black_concrete.json"]
            )
            self.assertIn(
                "fluid_pipe_display:pylon:new",
                {c["when"] for c in black["model"]["cases"]},
            )

            atlas = json.loads(
                files["assets/minecraft/atlases/items.json"]
            )
            resources = {
                s.get("resource")
                for s in atlas["sources"]
                if isinstance(s, dict)
            }
            self.assertIn("pylon:item/new", resources)
            self.assertIn("rebarmobs:item/new", resources)

            self.assertTrue(metadata["changed"])
            self.assertEqual(metadata["conflict_count"], 0)
            self.assertGreaterEqual(len(metadata["carrier_added"]), 3)
        finally:
            temp.cleanup()

    def test_local_conflict_is_preserved_and_reported(self):
        baseline_files = self.base_files()
        baseline_files["assets/minecraft/items/apple.json"] = item(
            [
                case("pylon:old_item", "pylon:item/local_fix"),
                case("other:keep_me", "other:item/keep"),
            ]
        )

        old = self.upstream_old()
        new = dict(old)
        new["assets/minecraft/items/apple.json"] = item(
            [case("pylon:old_item", "pylon:item/upstream_new")]
        )

        temp, _, output, metadata, report = self.run_import(
            baseline_files, old, new
        )
        try:
            files = read_zip(output)
            apple = json.loads(files["assets/minecraft/items/apple.json"])
            cases = {c["when"]: c for c in apple["model"]["cases"]}
            self.assertEqual(
                cases["pylon:old_item"]["model"]["model"],
                "pylon:item/local_fix",
            )
            self.assertEqual(metadata["conflict_count"], 1)
            self.assertIn("local Pylon case differs", report.read_text())
        finally:
            temp.cleanup()

    def test_upstream_deletion_is_review_only(self):
        baseline_files = self.base_files()
        old = self.upstream_old()
        new = dict(old)
        del new["assets/pylon/models/item/old.json"]

        temp, _, output, metadata, _ = self.run_import(
            baseline_files, old, new
        )
        try:
            files = read_zip(output)
            self.assertIn("assets/pylon/models/item/old.json", files)
            self.assertEqual(metadata["deletion_review_count"], 1)
        finally:
            temp.cleanup()


if __name__ == "__main__":
    unittest.main(verbosity=2)
