# Slimefun Legacy Resource Pack

Official combined resource pack for **Slimefun Legacy** on modern Minecraft Java.

The pack is designed for **Minecraft 1.21.11 through 26.3** and keeps vanilla
items/blocks intact while providing the custom models used by Slimefun Legacy,
its supported addons, Pylon/Rebar, Magic, MMOItems, and Slimefun Warfare.

## Permanent player download

```text
https://github.com/wickidcow/SFL_RP_Official/releases/latest/download/SlimefunLegacyRP.zip
```

The release asset name is always **`SlimefunLegacyRP.zip`** so Slimefun Legacy
can use one stable URL across future resource-pack releases.

## Confirmed working baseline

Version: **4.0.0**

SHA-1:

```text
ccb872b7a24984d3e3d0472d963ae0ae1b3fc1e5
```

SHA-256:

```text
1ad615e5a9bd6117e5010255601ddb44451c1ce124fa17c39d376617f775cdb8
```

The SHA-pinned baseline is also recorded in [BASELINE.json](BASELINE.json).

## Exact-reproduction rule

The confirmed ZIP is the source of truth.

When there are **no reviewed files under `overrides/` and no active entries in
`deletions.txt`**, the build does **not** unpack and recompress the archive.
It copies the pinned working baseline byte-for-byte to
`SlimefunLegacyRP.zip`.

GitHub Actions then verifies:

- the baseline SHA-1;
- the baseline SHA-256;
- the generated ZIP SHA-1;
- the generated ZIP SHA-256;
- a byte-for-byte `cmp` against the downloaded baseline.

That means a normal no-change build must reproduce the exact tested artifact,
not merely a ZIP with equivalent contents.

## Included content

The pack keeps Slimefun as the primary resource source and currently includes
the assets required by:

- Slimefun Legacy and its bundled/supported addon artwork
- Pylon
- Rebar and RebarMobs
- Magic
- MMOItems resource-pack content
- IAWeapons / Slimefun Warfare
- MC Icons
- ore texture overrides
- required Minecraft item definitions, equipment data, aliases, and modern overlays

The pack intentionally retains supporting namespaces when a model actually
depends on them. It does **not** run a global namespace-normalization pass.

## Why the build is conservative

Modern Minecraft separates item and block texture atlases more strictly than
older resource packs. During 26.x testing, broad atlas reconstruction and
ItemsAdder alias rewriting caused several regressions, including:

- every placed block rendering as the magenta/black missing texture;
- vanilla swords, bows, armor and spawn eggs being replaced or missing;
- player-head-backed guide icons breaking;
- Golden Sword CustomModelData entries selecting the wrong model;
- Chainmail inheriting non-vanilla artwork.

The current build system therefore starts from the **last tested, known-good
release** and applies only explicitly reviewed file changes.

## Updating the pack

Future changes are made in three stages:

1. Put replacement/addition files under `overrides/` using their exact
   resource-pack paths. Put removals in `deletions.txt`.
2. GitHub Actions builds a candidate from the SHA-pinned baseline and runs
   `tools/validate_pack.py`. Download and test the resulting
   **SlimefunLegacyRP** artifact in Minecraft.
3. After the candidate is confirmed in-game, publish that exact tested artifact
   through the release workflow. The release workflow validates the checksum
   again and uploads it unchanged as `SlimefunLegacyRP.zip`.

If no override or deletion is supplied, step 2 outputs the exact current
working ZIP byte-for-byte.

The build command used by Actions is equivalent to:

```bash
python tools/update_pack.py base.zip SlimefunLegacyRP.zip \
  --overrides overrides \
  --delete-list deletions.txt

python tools/validate_pack.py SlimefunLegacyRP.zip
```

## Regression checks

`tools/validate_pack.py` currently guards the working behavior that was
verified during 26.x testing:

- valid ZIP and modern `pack.mcmeta`
- no deprecated overlay `formats` keys
- required Slimefun/Pylon/Rebar/Magic/MMOItems/IAWeapons/MC Icons namespaces
- native player-head fallback remains intact
- no block sprites imported into the item atlas
- no item sprites imported into the block atlas
- Golden Sword keeps its Pylon, IAWeapons, Slimefun and ExtraGear mappings
- vanilla Golden Sword model/texture overrides are not reintroduced
- vanilla Chainmail texture overrides are not reintroduced
- Chainmail item definitions retain their vanilla fallback

## Source priority

When upstream assets conflict, the intended priority is:

1. Slimefun Legacy
2. Pylon / Rebar / RebarMobs
3. Magic
4. MMOItems
5. IAWeapons / Slimefun Warfare
6. MC Icons
7. ore overrides

Large generated ItemsAdder packs are used only as compatibility donors when a
specific generated model/alias is required; they are not used wholesale as the
base pack.

## License

See [LICENSE](LICENSE) and the licenses of the upstream projects whose assets
are included.
