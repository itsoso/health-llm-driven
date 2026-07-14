# Mobile Production Dependency Risk Review

Review date: 2026-07-14

## Decision

The production dependency audit has no critical vulnerability. The remaining findings are one transitive Markdown parsing chain with no upstream patched release available:

- `react-native-markdown-display`
- `markdown-it`
- `linkify-it`

The release may proceed to TestFlight with the controls below. App Review remains blocked by the real-device acceptance gate, not by these dependency findings.

## Controls

- All Agent Markdown rendering uses the shared `mobile/utils/safeMarkdown.ts` parser.
- Automatic linkification, typographer transformations and raw HTML parsing are disabled.
- Render input is capped at 50,000 characters before parsing.
- Direct Markdown render sites pass both the shared parser and the bounded source string.
- Production overrides pin patched XML, PostCSS and UUID dependencies.
- `npm audit --omit=dev` and the shared-parser tests are part of the release evidence.

## Residual Risk

An adversarial Markdown payload could still exercise vulnerable code inside the upstream parser. The current controls reduce the reachable parsing surface and cap resource use, but they do not replace an upstream fix. Before each App Store candidate:

1. Re-run `npm audit --omit=dev`.
2. Re-check whether `react-native-markdown-display`, `markdown-it` or `linkify-it` has a compatible patched release.
3. Block the release if a critical finding appears, the shared parser is bypassed, or audit findings expand beyond the documented chain.

Owner: Mobile release owner.
