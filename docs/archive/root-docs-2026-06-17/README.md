# Root Documentation Archive - 2026-06-17

This folder keeps historical Markdown files that previously lived at the
repository root.

They are preserved for traceability, but they are not the current product,
architecture, deployment, or operations entrypoints. Many of these files are
one-off fix reports, temporary deployment notes, old migration guides, or
legacy feature summaries.

Use the current docs instead:

- Product overview: [`../../../README.md`](../../../README.md)
- Current architecture: [`../../ARCHITECTURE.md`](../../ARCHITECTURE.md)
- Product PRD: [`../../prd/reva-personal-health-os-prd.md`](../../prd/reva-personal-health-os-prd.md)
- Health OS PDD: [`../../prd/2026-06-16-health-leverage-action-os-pdd.md`](../../prd/2026-06-16-health-leverage-action-os-pdd.md)
- Agent methodology: [`../../HARNESS.md`](../../HARNESS.md)
- Governance: [`../../governance/`](../../governance/)

Root directory policy after this cleanup:

- Keep only stable entrypoints and project manifests at repo root.
- Put evergreen documentation under `docs/`.
- Put stale root-level reports under `docs/archive/root-docs-YYYY-MM-DD/`.
- Do not add new root-level `*_FIX.md`, `*_SUMMARY.md`, `*_GUIDE.md`, or
  deployment report files.
