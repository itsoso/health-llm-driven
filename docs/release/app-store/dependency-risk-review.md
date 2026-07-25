# Mobile Production Dependency Risk Review

Review date: 2026-07-25

## Decision

The production dependency audit has no critical vulnerability. The remaining findings are:

- One transitive Markdown parsing chain with no compatible upstream patched release available: `react-native-markdown-display` -> `markdown-it` -> `linkify-it`.
- `brace-expansion` CVE-2026-14257 / GHSA-mh99-v99m-4gvg, reported through React Native, Expo configuration plugins, Jest and native-module build tooling.

The release may proceed to TestFlight with the controls below. App Review remains blocked by the real-device acceptance gate, not by these dependency findings.

## Controls

- All Agent Markdown rendering uses the shared `mobile/utils/safeMarkdown.ts` parser.
- Automatic linkification, typographer transformations and raw HTML parsing are disabled.
- Render input is capped at 50,000 characters before parsing.
- Direct Markdown render sites pass both the shared parser and the bounded source string.
- Production overrides pin patched XML, PostCSS and UUID dependencies.
- `npm audit --omit=dev` and the shared-parser tests are part of the release evidence.
- `brace-expansion` is not imported into the iOS application bundle and the app does not pass user-controlled patterns to Node `glob`, `minimatch` or `brace-expansion`. The finding is currently limited to build-time tooling.
- Mobile CI runs `scripts/npm-audit-gate.mjs` against `mobile/npm-audit-policy.json`. The gate resolves every high/critical transitive path to its advisory leaf, fails closed on malformed/unresolved/new advisories, and permits only GHSA-mh99-v99m-4gvg.
- The GHSA-mh99-v99m-4gvg exception expires on 2026-08-15. CI will turn red after that date unless the dependency is upgraded or the risk is explicitly re-reviewed with fresh evidence.
- Do not apply `npm audit fix --force`: the generated recommendation upgrades React Native across a breaking version boundary. Upgrade through the Expo compatibility matrix when a compatible dependency chain is available.

## Residual Risk

An adversarial Markdown payload could still exercise vulnerable code inside the upstream parser. A compromised or untrusted build input could also exercise the vulnerable Node glob chain. The current controls reduce the reachable parsing surface and keep the brace-expansion issue outside the shipped runtime, but they do not replace upstream fixes. Before each App Store candidate:

1. Re-run `node ../scripts/npm-audit-gate.mjs --policy npm-audit-policy.json` from `mobile/`.
2. Re-check whether `react-native-markdown-display`, `markdown-it`, `linkify-it` or the React Native/Expo build chain has a compatible patched release.
3. Block the release if a critical finding appears, the shared parser is bypassed, `brace-expansion` becomes runtime-reachable, or audit findings expand beyond the documented chains.

Owner: Mobile release owner.
