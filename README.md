# Slimefun Legacy Resource Pack

Combined resource pack for **Slimefun Legacy + Pylon + IAWeapons** on Minecraft Java **1.21.11+**.

## Latest player download

```text
https://github.com/wickidcow/SFL_RP_Official/releases/latest/download/SlimefunLegacyRP.zip
```

## Included

- Slimefun Legacy core models/textures
- Pylon models/textures
- IAWeapons models/textures/sounds
- required modern `assets/minecraft/items/` definitions
- required Pylon/IAWeapons atlas entries
- required IAWeapons internal helper models
- Slimefun armor/elytra equipment assets
- preserved player-head/skull special fallbacks
- purple Slimefun resource-pack icon

## Removed

Unrelated addon namespaces are intentionally excluded, including:

- Rebar / RebarMobs
- Supreme
- InfinityExpansion
- FluffyMachines
- Cultivation
- ExoticGarden
- Gastronomicon
- other unrelated generated ItemsAdder/ModelEngine content

## CustomModelData merge

This pack must support two different modern CustomModelData styles at the same time:

- **Slimefun + IAWeapons:** numeric/float CustomModelData
- **Pylon:** string CustomModelData

The build nests Pylon's string selector around the Slimefun/IAWeapons numeric range dispatcher so all three can safely share vanilla carrier items without overwriting one another.

## Head / skull compatibility

The merged item definitions preserve Minecraft's native special head fallbacks, including the player-head model:

```text
minecraft:head
kind: player
```

That prevents normal player heads and head-backed guide/category icons from being replaced by missing-model placeholders when no custom mapping matches.

## Compatibility

- Minecraft Java 1.21.11+
- modern `assets/minecraft/items/` item definition format
- validated against the current 26.3 resource-pack layout
- `pack_format: 75`
- `min_format: 75`

## Sources

The automated build currently uses:

- the previously validated Slimefun/IAWeapons source release from this repository
- the official Pylon resource pack release from `pylonmc/pylon-resource-pack`

## Build

```bash
python tools/build_combined_pack.py slimefun-source.zip pylon-source.zip SlimefunLegacyRP.zip
```

The build validates that Slimefun, Pylon, and IAWeapons mappings are all present, that the player-head fallback survived the merge, and that removed addon namespaces are not referenced.

## License

See [LICENSE](LICENSE).
