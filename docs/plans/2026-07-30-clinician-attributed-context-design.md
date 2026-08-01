# Clinician-Attributed Context Design

> Superseded for clinician-turn authorization by
> `docs/plans/2026-08-01-clinician-provenance-guard-design.md`. This document
> remains as the historical design record for the shared persistence, context
> and prompt boundaries.

## Goal

Make XiaoBa understand clinician diagnoses and assessments as provenance-bearing
health context instead of misclassifying them as incomplete symptom records.
Persist such context only when the user explicitly asks to record or save it.

## Root Cause

The failure is a contract mismatch across layers:

1. The intent classifier uses broad symptom words such as “痛” to infer both the
   domain and an implicit write.
2. The symptom extractor is intentionally narrower and rejects doctor/report
   language because it is not a current self-observation.
3. The fast-record path sees zero write receipts and replaces the model response
   with a generic request for record type and value.
4. The turn outcome becomes retryable, so Mobile displays “上一轮未完成”.

Each component behaves according to its local contract, but the system lacks a
semantic frame and tool for clinician-attributed facts.

## Approaches Considered

### 1. Change only the fallback copy

This would hide the most visible nonsense but keep the false symptom write,
failed turn, and missing clinician provenance. It is rejected as a symptom fix.

### 2. Reuse Clinical Journal and add a typed Agent capability

Add a `clinical_context` intent domain, route bare statements to the reliable
model, and expose the existing doctor-feedback service as a receipted Agent
tool for explicit saves. Add the latest saved clinician feedback to full health
context with a provenance label. This is the selected approach because it
connects existing architecture without a migration.

### 3. Create a new clinical-assessment model

A dedicated model could encode provider, encounter and confidence in more
detail, but it would duplicate `ClinicalJournalEntry` before the current
primitive is connected. It is deferred until a future structured encounter
feature needs fields the journal cannot represent.

## Architecture

### Architecture corrections

Three TDD and review cycles first showed that marker precedence could not safely
separate a user's command from a command quoted from a clinician. A deterministic
clause frame then replaced whole-text marker precedence. That fixed
punctuation-separated cases but failed another three review cycles because one
clause can contain multiple actions with different actors:

```text
我想记录饮食但医生说要保存诊断
医生说要保存诊断但请记录今天腰痛6分
```

Attaching one actor, target and polarity to a clause necessarily transferred
authority between those actions. Separate save and mutation reducers also
drifted: a late cancellation applied to save but not delete, and a noun
occurrence such as “诊断记录” could be interpreted as another save action.

The approved correction is an action-occurrence evidence model. Authorization
is resolved at the smallest semantic unit that can carry it: an individual
action occurrence.

The following alternatives were rejected:

1. Splitting on more conjunctions such as “但/然后/不过” remains a clause
   heuristic and still cannot represent nested or coordinated actors reliably.
2. Failing closed for every clinician-bearing multi-action sentence is safe but
   would make valid compound requests needlessly unusable.
3. An LLM semantic classifier may help response generation but is too
   non-deterministic, slow and expensive to carry medical write authority.

### Action evidence module

Create a pure deterministic `utterance_action_evidence.py` module. It consumes
raw text with original offsets and returns an ordered sequence:

```text
ActionEvidence
  span
  action
  actor: user | clinician | ambiguous
  target
  target_span
  polarity: positive | negative
  modality: command | question | statement
  provenance
```

Provider evidence is extracted independently of action vocabulary. Missing an
action synonym must not erase known clinician provenance or expose the raw
whole-text authorizer.

Each action occurrence resolves its own actor:

- a clinician reporting relationship governing the occurrence makes the actor
  `clinician`;
- a structurally scoped user command or “根据/依据/按照” basis construction
  makes the actor `user`;
- provider evidence before the occurrence without clear user authority makes
  the actor `ambiguous`.

Noun spans such as “医生诊断记录” and “用药记录” are excluded before save
evidence is created. Target resolution separates clinician basis/modifiers from
the actual action object.

#### Task 1B v2 correction: constrained candidates and actor scopes

The first occurrence extractor still collapsed every creation verb into one
generic family and inferred actor independently by looking backwards from each
verb. Independent specification review rejected that implementation: it made
creation verbs authorize unrelated product capabilities, allowed clinician
report scope to leak across a new top-level user command, and changed the
legacy classifier before the evidence reducer was integrated.

The corrected extractor therefore has two explicit internal contracts:

1. An action candidate carries its exact raw span and the set of action
   families that the matched verb already belongs to. Target resolution may
   select only a member of that set. A known media/plan/reminder target outside
   the verb's allowed families is an unresolved candidate and produces no
   authorizing `ActionEvidence`; it must never be rewritten into another
   family. Overlapping verbs such as “保存” retain all of their original
   memberships, so “保存康复计划” may resolve to `plan` while “保存诊断” remains
   `save`.
2. Actor ownership is assigned by one left-to-right scope pass. A
   provider-owned quote always remains clinician-owned, even when it contains
   “请/帮我”. An unquoted provider report owns its first and coordinated
   actions. It can switch back to the user only after a completed
   clinician-owned action and a top-level transition plus an explicit user
   command cue, or after a hard sentence boundary. Thus “医生说要保存诊断但请记录
   今天腰痛6分” has clinician then user actors, while “医生说「请记录今天腰痛」”
   remains clinician-owned.

Shared vocabulary has a legacy view and an evidence view in one lexicon
module. The legacy tuples and classifier behavior remain unchanged until Task
1C. Evidence-only question, negation, transition and family metadata may be
stricter, but the old classifier must not import those extensions. Candidate
coverage and property tests are derived directly from the structured evidence
view; no action family keeps a second handwritten verb subset.

#### Task 1B v3 correction: authorization-grade parsing

The v2 extractor passed specification review but failed adversarial quality
review because an unrecognized stance still defaulted to `command`, provider
scope was flat, and target/relative parsing still depended on finite marker
lists. Adding more question, negation or modifier words would recreate the same
fail-open boundary.

Task 1B therefore treats action evidence as an authorization proof rather than
a complete natural-language interpretation:

- `command` requires a positive structural proof. A top-level bare imperative,
  strict polite/user prefix, `把` disposal construction, first-person command,
  clinician basis command, or coordination from an already proven command may
  establish that proof. Unexplained prefixes and embedded action surfaces
  remain non-authorizing even when no known negation/question marker matches.
- Quote, provider report and basis scopes form a nested tree. A
  provider-owned quote or any enclosing active clinician report has higher
  priority than a local basis. Lower-priority evidence may tighten ownership but
  never upgrade clinician/ambiguous speech to user authority.
- Action groups identify governors, coordinated actions, embedded actions and
  action-like nouns before modality is assigned. Only governors and valid
  coordinated actions can receive command proof. Relative phrases and deletion
  history therefore cannot become mutations merely because their surface verb
  is in the action vocabulary.
- Target scope follows the governing action and actual action/boundary events.
  The right-hand head in a modifier chain wins without enumerating its
  intermediate verb. Different target kinds joined at the same object level
  fail closed as a conflict.

Parsing uses one lexical pass to index quote, provider, action, target, stance,
boundary and conjunction events. Scope linking, action grouping, target
resolution and stance resolution consume those ordered events with cursors;
per-action full-text rescans are forbidden. The intended bound is linear in
input plus emitted events.

The shared lexicon keeps byte-compatible legacy views for the public classifier
and typed evidence views for provider, report, basis, action-family, target and
stance metadata. Task 1B still must not change public classifier behavior.

Lexicon-derived property matrices prove vocabulary coverage. A separate fixed
security corpus, whose cases are not generated from implementation constants,
proves fail-closed behavior for nested providers, unknown stance, embedded
actions, target conflicts and all prior review findings.

### Evidence reduction

Save, delete, update and sync share one target-aware stance reducer:

- evidence is grouped by compatible target and ordered by source position;
- a later negative stance cancels only a compatible earlier positive stance;
- question modality never grants authority;
- clinician and ambiguous evidence may inform response context but never
  authorize a tool;
- a user save may refer to immediately preceding clinician content;
- destructive operations require their own explicit target.

Read, media, plan and reminder actions use the same actor-resolved evidence
sequence rather than a separate whole-text path. Clinician-bearing input must
never fall back to raw whole-text authorization. Text with no clinician evidence
continues through the existing general classifier.

The classifier maps the final active evidence to the existing public
`IntentFrame`; persistence models and public contracts do not change. The
reliable model still owns natural-language response generation. Deterministic
evidence owns routing and authorization only.

### Intent boundary

Clinician-attribution markers such as “医生诊断”, “医生说”, “医生认为”,
“医生评估”, “康复师认为” and “检查提示” are evaluated before symptom domain
inference.

- Bare statement: `chat / clinical_context / acknowledge`
- Question or advice request: `advice / clinical_context / analyze`
- Explicit record/save command: `write / clinical_context / create`, with a
  reliable tool-capable model required

The same sentence may still contain symptom terms, but provenance wins over the
keyword because it changes both persistence semantics and medical authority.

### Tool boundary

Add model-visible `record_doctor_feedback`:

- inputs: `summary`, `assessment`, `plan`, `visit_date`;
- at least one text field is required;
- capability policy allows it only for an explicit write intent;
- adapter delegates to `record_doctor_feedback`;
- success returns a positive resource ID and
  `resource_type=clinical_journal_entry`;
- the normal Agent runtime operation and receipt machinery owns dispatch,
  identity verification and honest completion.

The tool does not create a `HealthProblem`, prescribe treatment, or infer risk.

### Context boundary

Full personalized health context includes a small, recent set of
`created_by="doctor"` entries. Each line is prefixed as user-reported clinician
feedback and length-bounded. Pure knowledge questions using the minimal context
budget do not receive these entries.

After a successful tool write, the per-user health-context cache is invalidated
so the next turn can see the new entry.

### Prompt behavior

The Agent prompt explicitly requires:

- preserve clinician attribution;
- reflect the stated causal chain without endorsing it as Reva's diagnosis;
- do not auto-save bare statements;
- use `record_doctor_feedback` only after explicit save language;
- do not redirect structured medical facts to `remember`.

## Data Flow

```text
User sentence
  -> provider spans + ordered ActionEvidence
  -> actor/target/polarity/modality per occurrence
  -> target-aware stance reduction
  -> bare or ambiguous clinician context ----> reliable response, no write
  -> active user "记录/保存" evidence
       -> record_doctor_feedback tool
       -> ToolGateway explicit-write check
       -> doctor_report_service
       -> ClinicalJournalEntry(created_by=doctor)
       -> verified receipt
       -> invalidate full health context cache
       -> provenance-bearing recall on later turns
```

## Error Handling

- Evidence parsing is deterministic and local; it does not call an LLM.
- Ambiguous actor, target or modality fails closed to a non-write
  `clinical_context` turn.
- Parsing does not emit user-visible exceptions or log the clinical text.
- Raw offsets, punctuation, conjunctions and newlines are preserved before text
  normalization.
- Clinician evidence disables raw whole-text write/mutation fallback even when
  no known action is found.
- Missing all text fields: structured local rejection; no dispatch.
- Missing user identity: structured local rejection; no dispatch.
- Invalid visit date: structured local rejection with correction guidance.
- Persistence error: rollback, log only exception type/no clinical text, and
  return an observable failure; never claim success.
- No tool call on a bare statement: normal chat completion, not a failed action.
- No receipt after an attempted explicit write: existing honesty gate reports
  that the write was not verified.

## Testing

TDD covers each boundary independently:

1. An action-evidence matrix crosses actor (user/clinician/ambiguous), action
   family, target, polarity and modality.
2. The exact screenshot sentence classifies as `clinical_context` and is not
   fast-record eligible.
3. Same-sentence multi-actor and multi-action permutations prove that every
   occurrence keeps independent authority.
4. Save/delete/update/sync synonyms are crossed with negative, interrogative and
   late-cancellation stances.
5. Noun “记录” spans never become save actions.
6. Clinician basis before/after a medication, symptom, media, plan or reminder
   target does not override the real target.
7. Different targets do not cancel or authorize one another.
8. A structural canary fails if clinician-bearing input reaches the legacy raw
   whole-text authorizer.
9. Explicit user read/delete/update and ordinary current symptoms retain their
   existing behavior.
10. Tool schema, registry and capability policy expose only the intended write.
11. Adapter validation and persistence produce an owner-scoped verified receipt.
12. Full context recalls saved feedback with provenance; minimal context omits
   it; cache invalidation makes the next turn fresh.
13. Focused Agent streaming regression proves the original sentence no longer
   reaches the record-details fallback.

## Rollout

Backend-only deployment. No schema migration and no Mobile release. Verify the
original sentence and an explicit-save sentence through the production Agent
path, then ask the user to confirm the Mobile behavior before closing G6.
