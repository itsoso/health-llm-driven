# Mini Program Security Quarantine

The mini-program source is retained for product history, but its Taro dependency tree is not part of any approved build, deployment, or release path. On 2026-07-21 the production audit reported critical and high vulnerabilities without a coherent non-breaking Taro resolution.

`package.json` therefore contains no runtime or build dependencies and every build/deploy command fails loudly. Re-enabling this surface requires a current framework baseline, a zero-high production audit, authentication/privacy review, CI coverage, and an explicit update to the system/product maps.
