# Clinician Formal Gap Hardening Design

## Goal

Close the remaining Unicode-category bypasses in clinician-basis mutations
without rejecting obfuscated text that is merely payload inside an already
validated explicit doctor-feedback write.

## Canonical clause contract

For each NFKC-compatible character, the guard first flushes on an existing
hard or question boundary. It then retains only Unicode letters and numbers
(`L*` and `N*`) in the clause-local canonical view. Every other category is a
gap. Raw source offsets remain attached to retained characters, and gaps never
join text across a flushed boundary or an excluded authorization envelope.

This positive whitelist covers controls, private-use characters,
noncharacters, marks, symbols, separators, and punctuation without maintaining
an incomplete denylist.

## Validated content opacity

The explicit-feedback parser remains the authority for the outer envelope:
command, clinician object, content bounds, negation, question form, and exact
compound actions. Only content from a candidate whose status is already
`valid` is opaque to the general obfuscation detector. The detector still scans
the command and clinician object, and invalid/coordinated candidates receive no
opacity.

Consequently, payload text such as `根据医★生建议调★整训练强度` is preserved
byte-for-byte in a single verified feedback write, while an obfuscated command
or clinician object and content with an exact appended tool action remain
fail-closed.

## Verification

- Fixed safety fixture and classifier assertions for Cc, Co, Cn/noncharacter,
  content opacity, and command/object controls.
- Capability, zero-schema stream, direct gateway, and end-to-end stream checks
  for every Unicode bypass.
- Verified-receipt tests assert one row and exact raw content preservation.
- Relevant expanded regression, Ruff, py_compile, JSON validation, pre-commit,
  and an independent safety/code review before commit.
