from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

import fix_slimefun_model_aliases as fixer
import validate_pack as validator


class SlimefunAliasFixTest(unittest.TestCase):
    def make_tree(self, root: Path, texture_ref: str = "slimefun:slimefun/talisman1/wise") -> Path:
        atlas = root / "ia_overlay_modern_atlas/assets/minecraft/atlases/items.json"
        atlas.parent.mkdir(parents=True, exist_ok=True)
        atlas.write_text(
            json.dumps(
                {
                    "sources": [
                        {
                            "type": "single",
                            "resource": "slimefun:slimefun/talisman1/wise",
                            "sprite": "_slimefun:slimefun/talisman1/wise",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        model = root / "assets/slimefun/models/slimefun/talisman1/wise.json"
        model.parent.mkdir(parents=True, exist_ok=True)
        model.write_text(
            json.dumps(
                {
                    "parent": "minecraft:item/generated",
                    "textures": {
                        "layer0": texture_ref,
                        "particle": "#layer0",
                    },
                    "note": "slimefun:slimefun/talisman1/wise must not be rewritten outside textures",
                }
            ),
            encoding="utf-8",
        )
        return model

    def zip_tree(self, root: Path, output: Path) -> None:
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for path in root.rglob("*"):
                if path.is_file():
                    zf.write(path, path.relative_to(root).as_posix())

    def test_rewrites_only_texture_values_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model = self.make_tree(root)

            aliases = fixer.collect_slimefun_sprite_aliases(root)
            self.assertEqual(
                aliases["slimefun:slimefun/talisman1/wise"],
                "_slimefun:slimefun/talisman1/wise",
            )

            changed, refs = fixer.patch_models(root, aliases)
            self.assertEqual(refs, 1)
            self.assertEqual(
                changed,
                ["assets/slimefun/models/slimefun/talisman1/wise.json"],
            )

            data = json.loads(model.read_text(encoding="utf-8"))
            self.assertEqual(
                data["textures"]["layer0"],
                "_slimefun:slimefun/talisman1/wise",
            )
            self.assertEqual(data["textures"]["particle"], "#layer0")
            self.assertEqual(
                data["note"],
                "slimefun:slimefun/talisman1/wise must not be rewritten outside textures",
            )

            changed_again, refs_again = fixer.patch_models(root, aliases)
            self.assertEqual(changed_again, [])
            self.assertEqual(refs_again, 0)

    def test_conflicting_aliases_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_tree(root)
            second = root / "albion_26_3/assets/minecraft/atlases/items.json"
            second.parent.mkdir(parents=True, exist_ok=True)
            second.write_text(
                json.dumps(
                    {
                        "sources": [
                            {
                                "type": "single",
                                "resource": "slimefun:slimefun/talisman1/wise",
                                "sprite": "_slimefun:conflicting/wise",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                fixer.collect_slimefun_sprite_aliases(root)

    def test_alias_validator_rejects_direct_resource_and_accepts_fixed_sprite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "tree"
            root.mkdir()
            self.make_tree(root)

            broken = Path(tmp) / "broken.zip"
            self.zip_tree(root, broken)
            errors = validator.validate_aliases_only(str(broken))
            self.assertTrue(
                any("atlas resources instead of" in error for error in errors),
                errors,
            )

            aliases = fixer.collect_slimefun_sprite_aliases(root)
            fixer.patch_models(root, aliases)
            fixed = Path(tmp) / "fixed.zip"
            self.zip_tree(root, fixed)
            self.assertEqual(validator.validate_aliases_only(str(fixed)), [])


if __name__ == "__main__":
    unittest.main()
