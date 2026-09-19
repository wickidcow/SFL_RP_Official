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

## Releasing an update

1. Replace/update the source resource pack.
2. Increase the version in `VERSION`.
3. Push the change to `main`.
4. GitHub Actions downloads and validates the pack, then publishes it as `SlimefunLegacyRP.zip` on the corresponding release.

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
