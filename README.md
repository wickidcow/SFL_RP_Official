# Slimefun Legacy Resource Pack (Unofficial)

Unofficial resource pack distribution for **Slimefun Legacy**.

## Player download

Use the permanent latest-release URL:

```text
https://github.com/wickidcow/SFL_ResourePack_UnOfficial/releases/latest/download/SlimefunLegacyRP.zip
```

Minecraft clients should receive **SlimefunLegacyRP.zip** only.

The matching server-side model mapping belongs at:

```text
plugins/Slimefun/item-models.yml
```

The YAML mapping is server-side configuration and is not part of the resource-pack download sent to players.

A reference copy is kept in this repository at [`server/item-models.yml`](server/item-models.yml). Slimefun Legacy bundles the matching mapping so the live server file is created/updated under `plugins/Slimefun/item-models.yml`.

## Automatic pack repair

Before each release, GitHub Actions repairs the trimmed source pack so retained Slimefun/Pylon/Rebar assets do not point at namespaces that were removed during trimming.

The release pipeline currently:

- restores addon texture references from internal aliases such as `_slimefun:`, `_pylon:`, and `_b_pylon:` to their retained namespaces;
- sends copied vanilla model textures back to Minecraft's built-in `minecraft:` namespace instead of missing `_minecraft:` resources;
- repairs vanilla model parents such as `item/generated`, `item/handheld`, and `block/cube_all`;
- supplies transparent helper textures used by generated models;
- validates the reachable modern item-model graph and fails the release if a model or texture is still missing;
- replaces `pack.png` with the purple Slimefun Legacy icon.

This specifically prevents the magenta/black missing-texture squares that can otherwise appear on both Slimefun items and ordinary vanilla blocks on current 26.x clients.

## Releasing an update

1. Replace/update the source resource pack.
2. Increase the version in `VERSION`.
3. Push the change to `main`.
4. GitHub Actions downloads the source ZIP, repairs modern namespace/model references, validates the final pack, applies the purple pack icon, and publishes it as `SlimefunLegacyRP.zip` on the corresponding release.

The publish workflow can also be run manually with a custom ZIP source URL.

## Current bootstrap source

The initial GitHub release is bootstrapped from:

```text
http://overlord.kicks-ass.org:8163/SlimefunLegacyRP.zip
```

After the GitHub release is available, Slimefun Legacy can use the permanent GitHub `releases/latest/download` URL for player delivery.

## Compatibility

The current pack/model mapping has been verified in use with Minecraft **1.21.11 through 26.3**.

## License

See [LICENSE](LICENSE).
