# Agent interaction quality replay fixture

`corpus.json` is a synthetic release-gate fixture. It contains 20 intent-level
turns and represents five assistant surfaces per turn (100 surfaces total).

Allowed fields are limited to intent labels, output-shape booleans, terminal
state agreement, receipt/safety booleans, dedupe counters, timing buckets, and
synthetic character counts. Production prompts, assistant prose, images, user
or database identifiers, tokens, secrets, and database exports are forbidden.

Run from the repository root:

```bash
python3 scripts/replay_agent_interaction_quality.py
```

The timing values are synthetic contract fixtures. They verify threshold logic
and prevent release-rule drift; they are not production latency measurements.
