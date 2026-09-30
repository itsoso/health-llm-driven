# HTML presentation suffix query incident

| Field | Value |
| --- | --- |
| 状态 | building |
| 当前阶段 | G4 passed; awaiting coordinated release |
| Controller | health-harness-orchestrator |
| Overlay | safety-gate |

## G1 / G2

裁决: PASS. Run `html-query-scope-20260930`.

The reported sleep query succeeds without a format request but fails with
`,HTML 形式表达` or `，用HTML形式表达`. The source parser mistakes the format
suffix for an unresolved data filter and the capability gateway correctly
denies that unresolved scope. This is a bounded correction to presentation
projection, not new read authority or an expanded date/filter grammar.

Isolated worktree based on freshly fetched main
`b75afb476ba11be0beec9416f223932635d9a35d`; shared checkout untouched.
Only a complete standalone HTML presentation suffix is projected from the
original input, before quoted material removal. The entire remaining request
still passes owner, date, negation, mutation and residue checks. Original user
text remains in the envelope, provider input and conversation persistence.

## G3

- RED: 17 failed / 189 passed before the production edit, reproducing both
  scope resolution and actual gateway denial (`/tmp/reva-html-suffix-red.log`).
- Focused SQLite: 596 passed / 12 PostgreSQL-only skips, exit 0
  (`/tmp/reva-html-suffix-green.log`).
- Real Pi protocol with scripted model output, actual executor/gateway, owned
  database reader and message persistence: four passed. Synthetic rows prove
  another user's data and out-of-window records are excluded. Unsupported
  foreign-owner and extra-filter requests cause zero data dispatches. This
  tests execution and original format preservation, not a live model's HTML.
- PostgreSQL 16, isolated disposable database: all six focused suites,
  including the Pi runtime cases and prior PostgreSQL-only cases: 612 passed,
  zero skips, exit 0 (`/tmp/reva-html-postgres.log`).
- CI-mode integration (`DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai`):
  user workflow, coherence, recovery and new runtime cases: 22 passed, exit 0
  (`/tmp/reva-html-ci-integration.log`). No production health data used.
- LLM change gate passed, live model gate not required: no prompt/provider
  change. System Map wrapper passed; no architecture or schema changes.
- Secret scan and diff whitespace check passed.

## G4 / G5 / G6

Independent review on `9d19350dec81edbc730528139b872578118f1143`: NO-GO.
The projector stripped indentation before interpreting original material roles,
allowing a code-only request plus HTML suffix to dispatch. Added 100 matrix cases
covering four spaces, tabs, mixed whitespace and multiline code, both legacy
wrappers and new suffixes, query/batch and enforce/shadow. RED: 80 failures /
20 passes (`/tmp/reva-html-material-red.log`). The corrected projector requires
the shared read-authority parser, run on the untouched source, to preserve the
whole source before any presentation projection. It cannot reconstruct removed
material. Fresh focused SQLite: 700 passed / 12 PostgreSQL-only skips.
Three additional real Pi cases cover indentation. Final PostgreSQL: 715 passed,
zero skips, exit 0 (`/tmp/reva-html-postgres-v2.log`); CI-mode integration:
25 passed, exit 0 (`/tmp/reva-html-ci-integration-v2.log`). LLM change gate and
commit checks passed on the corrected source.

Independent G4 GO binds `046361e730534c345f3e568ee8d0be83f2573dce`: reviewer
independently ran 313 passing tests, 195 differential request pairs with zero
new or expanded scope, and 60 real gateway counterexamples with zero dispatch.
No production code changed after that review; this evidence update is docs only.

This repair is not deployed.
Another publisher was actively staging main on the production host; no SSH,
main push, release credential rotation or production mutation belongs to this
incident run. Existing login/security release and host-hardening work remain
separate pending release obligations; public registration remains blocked by
its existing security gate. Coordinate publication before changing main.
