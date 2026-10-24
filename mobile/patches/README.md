# Security and compatibility patches

`zod+4.6.6.patch` is a local backport for the v3 compatibility entry point, not a
claim that upstream Zod 4.6.6 fixed v3. The upstream GHSA-mrhx-c7xc-m3w5 fix
(a0ebf97, PR 6652) changes v4 only. v3 still traverses every element after an
array/set upper-bound failure. This patch returns INVALID immediately for
array.max, oversized array.length, and set.max/size in both CJS and ESM. Inputs
within the upper bound and lower-bound validation keep their existing behavior.
Unbounded collections remain unbounded; callers must choose limits appropriate
to their inputs. v3 maps do not expose the v4 size-limit API and are unchanged.

`expo++@expo+cli+55.0.33.patch` changes only the MCP schema factory to use that
hardened v3 entry point. @expo/mcp-tunnel 0.2.4 converts a v3 object shape with
zod-to-json-schema; supplying a v4 child silently loses its JSON-schema constraints.
Plugin and output validation remain on upstream v4. No optional MCP server is
installed or enabled by this change.

`npm ci` runs the existing fail-closed patch-package postinstall. CI also runs
`node --test scripts/security-dependency-compat.node.cjs`: sync/async CJS/ESM
upper bounds must reject without walking elements, and the real Expo factory
must retain command enum, scalar parameter types, required command and strict
additionalProperties through the real converter. The test dependency
zod-to-json-schema 3.25.2 falls within the tunnel's declared ^3.24.6 range.
The tests fail against a fresh installation without these patches.

Sources:
- https://github.com/advisories/GHSA-mrhx-c7xc-m3w5
- https://github.com/colinhacks/zod/commit/a0ebf97
- https://github.com/advisories/GHSA-27r3-jxmh-p828
