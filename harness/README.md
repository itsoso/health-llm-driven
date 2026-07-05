# Harness Registry

This directory declares the project-level eval, smoke, and operating-harness gates in `registry.json`.

The manifest is data-only: listing it must not run tests, call LLMs, hit the network, or mutate local state. Each entry should describe an existing command and mark live or costly requirements in `requires`.

Common fields:

- `stage`: one of `commit`, `ci`, `runtime`, `manual`, `release`.
- `command`: argv-style command list.
- `working_dir`: optional repo-relative cwd for monorepo commands, for example `backend`.
- `tags`: selectors such as `memory`, `eval`, `smoke`, `release`.
- `read_only`: whether listing/running the command is expected not to mutate product state.
- `blocking`: whether failure should block a handoff, CI gate, or release.
- `evidence_paths`: repo-relative files that define or verify the harness.

Local listing CLI:

```bash
python3 scripts/list_harnesses.py
python3 scripts/list_harnesses.py --json --tag memory
python3 scripts/list_harnesses.py --stage ci
```

This project owns both the manifest and the listing entry point. Cross-repo CLIs are useful for migration checks, but normal health work should stay self-contained inside this repository.
