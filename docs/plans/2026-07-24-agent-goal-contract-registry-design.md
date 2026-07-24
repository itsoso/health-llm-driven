# Agent Goal Contract Registry Design

## Context

Reva already freezes each turn into `AgentEnvelope`, `ExecutionContext`,
`IntentFrame`, and `TurnSnapshot`. Complex diet correction also has a typed
`GoalSpec` and deterministic read-back verification. The remaining extension
problem is that goal compilation, prompt obligations, and postcondition
verification are hard-coded in facade functions.

Adding another verified task currently requires editing several central
conditionals. That makes it easy to add a compiler without its verifier, or a
verifier without a user-safe execution contract.

## Decision

Introduce small, immutable registries inside Agent Kernel:

- `GoalCompilerRegistry` evaluates named compilers in a deterministic order.
- `GoalPromptRegistry` resolves a prompt renderer by exact goal kind.
- `GoalVerifierRegistry` resolves a postcondition verifier by exact goal kind.

The registries are static Python objects assembled at import time. They reject
duplicate names or kinds and expose only read-only inspection methods. They do
not support runtime plugin loading.

Existing public facades remain stable:

- `compile_goal_spec(...)`
- `format_goal_contract_prompt(...)`
- `verify_goal_postconditions(...)`

The existing diet recalculation behavior moves behind these registries without
changing its model prompt, write policy, receipt requirements, or read-back
rules.

## Safety Invariants

1. Compiler order is explicit and deterministic.
2. Duplicate compiler names and duplicate goal kinds fail during construction.
3. A goal that requires verification but has no registered verifier fails
   closed with `unsupported_goal_verifier`.
4. A missing prompt renderer produces no hidden authority or fallback prompt.
5. Registry metadata contains no user health content.
6. Client protocols, Runtime persistence, and iPhone local-closure behavior do
   not change.

## Alternatives Considered

### Keep central conditionals

Smallest code change, but every domain increases coupling and omission risk.
Rejected because it does not create a reliable extension boundary.

### Dynamic plugin discovery

Allows external registration, but introduces import-order, trust, and
production reproducibility risks. Rejected for the current monolith.

### One large universal handler object

Could bundle compiler, renderer, and verifier, but a compiler may emit control
goals such as `clarify` or `chat`, while only one resulting goal kind needs
postcondition verification. Separate typed registries preserve this distinction
without forcing placeholder handlers.

## Verification

- Registry unit tests cover deterministic selection and duplicate rejection.
- Facade tests prove diet compilation and prompt rendering are unchanged.
- Postcondition tests prove registered dispatch and fail-closed behavior.
- Existing stateful trajectory and Agent Kernel regression gates remain green.
