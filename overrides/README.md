# Reviewed Resource-Pack Overrides

Place only reviewed replacement/addition files in this directory using their exact
resource-pack path.

Examples:

```text
overrides/assets/slimefun/models/...
overrides/assets/minecraft/items/...
overrides/sfl_26_1_plus/assets/minecraft/items/...
```

`tools/update_pack.py` layers these files over the SHA-pinned known-good release
from `BASELINE.json`. Files are never bulk-renamed, namespace-normalized, or
automatically moved between the item and block atlases.

For removals, use `deletions.txt` instead of adding placeholder files.

After a build, `tools/validate_pack.py` checks the regressions that were found
during Minecraft 26.x testing, including:

- block sprites accidentally registered in the item atlas;
- item sprites accidentally registered in the block atlas;
- deprecated resource-pack overlay metadata;
- loss of the native player-head fallback;
- loss of Golden Sword/Pylon/IAWeapons/Slimefun mappings;
- accidental vanilla Golden Sword and Chainmail texture/model overrides.

Only promote an Actions artifact after it has also been tested in-game.
