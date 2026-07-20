# Validation status

The benchmark module is validated in two stages:

1. GitHub Actions compiles and packages the standalone Forge 1.20.1 companion mod.
2. The resulting jar must be tested in game beside the exact private Immersive Aircraft and Warfare Wings builds.

The fixed-input test rejects a result when its post-pilot Mixin control heartbeat is not observed, preventing an apparently successful report from being generated when the compatibility hook is inactive.
