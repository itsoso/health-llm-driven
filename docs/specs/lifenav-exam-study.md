# LifeNav 备考学习

Status: Web published; native extension verification pending. Updated: 2026-10-24.

## Decision and admission

Explicit user-requested LifeNav personal learning extension: daily 60-minute study for management comprehensive and English II, starting at approximately CET-4 English. Existing planning lacks exercise feedback.

RequirementAdmission: plan → practice → record → review; authenticated workspace tasks as source of truth; owner-scoped writes with safety overlay; explicit edit/save autonomy; no medical objects or claims. Success means saved plans/attempts survive reload and resolved mistakes retain explanation. Daily burden is 60 minutes; a complete mock requires three uninterrupted hours.

## Objects and contracts

Web offers 30 minutes English, 20 minutes rotating math/logic/writing, 10 minutes review. Existing LifeTask fields and role `other` store plans and attempts. Stable date/key UUIDs make insertion idempotent; persisted key codes must never be reordered/reused. First and latest same-day answers are retained; separate dates remain separate records. Latest dated task status determines the wrong-answer queue.

Existing backend ownership, revision CAS, undo/history and account-switch isolation apply. No API/schema/migration/health object changes, external LLM calls, notifications or client-side persistent storage. Existing size limits apply; capacity errors precede partial plan creation.

## User flow and safety

Open 备考学习 → add plan → study/answer → read explanation → explicitly save workspace → reload. Starting focus invokes the existing workspace save. Completion is self-reported; warm-up accuracy is not an exam score or admission prediction. Questions are original and labeled as foundational. Official university past-paper links do not include personal data. The exam date belongs to this cycle; planning stops at the exam date and admission-ticket details take precedence.

Non-goals: guaranteed admission, automatic essay grading, medical advice, enrollment submission. No copyrighted paper text is copied.

## Acceptance and verification

Repeated insertion produces three tasks totaling 60 minutes and preserves results. Wrong answers enter review; correct retries keep feedback visible and preserve prior attempts. Authenticated revisioned save/reload restores records. Existing conflict/account-switch tests remain green.

Run frontend tests, TypeScript, ESLint and production build; independent safety review; exact main CI; canonical no-backup frontend publication; browser readback. The native extension uses the same API and task identities. OTA delivery requires the same exact green SHA deployed on the backend under trusted release rules. No backup or schema migration; failed releases retain original lease/receipt under deployment governance.


## Native extension

User explicitly requested both mobile Web and native Reva. The native LifeNav workspace adds a 备考学习 tab with plan/result editing, focus timer, original practice and explanations, wrong-answer filtering and official resources. Existing owner-scoped save, account remount, background hiding and revision conflict preservation apply. No native dependency or runtime configuration change.

The native pure model mirrors Web with an executable parity check for persisted IDs, questions and rules. This follows the existing separate platform model layout without introducing a Metro cross-root dependency. Both clients use identical date/key UUIDs and share the server ledger. Native writes clone without pre-creating weeks so capacity checks remain atomic. Resource links use the OS browser and surface failures.
