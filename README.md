# SFL IAWeapons Resource Pack

Clean, focused **IAWeapons-only** resource pack for Minecraft Java **1.21.11+**.

This repository intentionally no longer publishes the old full Slimefun/Pylon/Rebar texture bundle. The current release pack contains only IAWeapons and the files required for IAWeapons to render correctly.

## Latest download

```text
https://github.com/wickidcow/SFL_RP_Official/releases/latest/download/SFL_IAWeaponsRP.zip
```

## Compatibility

- Minecraft Java **1.21.11** — resource pack format 75
- Minecraft **26.1 / 26.1.2** — format 84
- Minecraft **26.2** — format 88
- Minecraft **26.3** — current 97.x resource-pack structure
- Uses the modern `assets/minecraft/items/` item-definition system
- Designed to remain loadable on later formats through `min_format: 75`

## What is included

The generated ZIP contains:

- `assets/iaweapons/`
  - IAWeapons models
  - IAWeapons textures
  - IAWeapons sounds
- four vanilla carrier item definitions required by IAWeapons:
  - `crossbow`
  - `golden_sword`
  - `snowball`
  - `stick`
- ItemsAdder-generated firework-launcher item-context helper models
- a minimal modern item atlas containing only vanilla item sprites + IAWeapons sprites
- the updated purple Slimefun-style `pack.png`

## What is removed

The release ZIP does **not** include:

- Slimefun core models/textures
- Pylon
- Rebar / RebarMobs
- InfinityExpansion / InfinityExpansion2
- Supreme
- FluffyMachines
- Cultivation
- ExoticGarden
- Gastronomicon
- other unrelated addon/resource-pack namespaces
- ModelEngine content

This prevents the pack from overriding unrelated vanilla or Slimefun item models.

## Preserved IAWeapons CustomModelData

| Carrier | CustomModelData | IAWeapons model |
| --- | ---: | --- |
| Crossbow | 10000 | Shotgun |
| Crossbow | 10001 | Firework Launcher |
| Golden Sword | 1981823 | AK47 |
| Golden Sword | 1981824 | Hand Gun |
| Golden Sword | 1981828 | Revolver |
| Snowball | 9928315 | Grenade |
| Stick | 10029 | Clip |
| Stick | 10079 | Shotgun Cartridge |
| Stick | 10080 | Projectile |

## Release process

The GitHub Action downloads a source pack, runs `tools/build_iaweapons_pack.py`, validates the resulting resource graph, and publishes:

```text
SFL_IAWeaponsRP.zip
```

The build fails if a removed addon namespace is still referenced or if the expected IAWeapons CustomModelData mapping changes.

The default bootstrap source for the 2.0 clean rebuild is the prior v1.0.1 full resource-pack release. A different source ZIP can be supplied manually when IAWeapons assets need to be refreshed.

## Local build

```bash
python tools/build_iaweapons_pack.py source-pack.zip SFL_IAWeaponsRP.zip
```

## License

See [LICENSE](LICENSE).
