# Intake Intent Router Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a shared intake intent router so "吃了" text is safely classified as diet, medication, supplement, water, diet management, or unknown before any dynamic card or write path is generated.

**Architecture:** Add a deterministic classifier in `backend/app/services/intake_intent_classifier.py` and reuse it from inline cards and tool validation. Add server-generated medication draft cards and a mobile native renderer that uses the existing safe manual-confirm card action system.

**Tech Stack:** Python 3.12, FastAPI service layer, pytest, React Native/Expo, Jest, existing chat card registry/action runtime.

---

### Task 1: Shared Intake Intent Classifier

**Files:**
- Create: `backend/app/services/intake_intent_classifier.py`
- Test: `backend/tests/test_intake_intent_classifier.py`

**Step 1: Write failing classifier tests**

Create `backend/tests/test_intake_intent_classifier.py`:

```python
import pytest

from app.services.intake_intent_classifier import classify_intake_intent


@pytest.mark.parametrize(("query", "kind"), [
    ("记录午餐吃了牛肉面", "diet"),
    ("午餐吃了煎牛肉能量碗 770kcal", "diet"),
    ("记录刚吃了替普瑞酮", "medication"),
    ("刚服用了替普瑞酮胶囊（施维舒）", "medication"),
    ("记录刚吃了奥美拉唑20mg", "medication"),
    ("吃了鱼油", "supplement"),
    ("吃了维生素D3", "supplement"),
    ("喝了300ml水", "water"),
    ("删除这一餐", "diet_management"),
    ("我刚才不小心删除了", "diet_management"),
    ("刚吃了一个东西", "unknown"),
])
def test_classifies_common_intake_phrases(query, kind):
    result = classify_intake_intent(query)

    assert result.kind == kind
```

**Step 2: Verify test fails**

Run:

```bash
cd backend
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai venv/bin/pytest tests/test_intake_intent_classifier.py -q
```

Expected: FAIL because module does not exist.

**Step 3: Implement minimal classifier**

Create `backend/app/services/intake_intent_classifier.py`:

```python
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class IntakeIntent:
    kind: str
    confidence: float
    reason: str
    text: str = ""
    slots: dict[str, Any] = field(default_factory=dict)


_MEDICATION_MARKERS = (...existing medication marker tuple...)
_SUPPLEMENT_MARKERS = ("鱼油", "维生素", "维C", "维D", "D3", "B族", "益生菌", "镁", "NAC")
_DIET_MANAGEMENT_MARKERS = (...existing delete/undo marker tuple...)


def classify_intake_intent(query: str) -> IntakeIntent:
    raw = str(query or "").strip()
    normalized = re.sub(r"\s+", "", raw).lower()
    if not normalized:
        return IntakeIntent("unknown", 0.0, "empty")

    if _looks_like_diet_management(normalized):
        return IntakeIntent("diet_management", 0.95, "diet_management", raw)
    if _looks_like_water(normalized):
        return IntakeIntent("water", 0.9, "water", raw, {"amount_ml": _extract_water_amount(normalized)})
    if _looks_like_medication(normalized):
        return IntakeIntent("medication", 0.9, "medication_marker", _extract_item_text(raw), _extract_medication_slots(raw))
    if _looks_like_supplement(normalized):
        return IntakeIntent("supplement", 0.82, "supplement_marker", _extract_item_text(raw))
    if _looks_like_diet(raw, normalized):
        return IntakeIntent("diet", 0.82, "diet_marker", _extract_item_text(raw), {"meal_type": _infer_meal_type(raw)})
    return IntakeIntent("unknown", 0.35, "ambiguous", raw)
```

Use the exact medication regexes currently duplicated in `inline_cards.py` and `tool_validator.py`.

**Step 4: Verify tests pass**

Run:

```bash
cd backend
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai venv/bin/pytest tests/test_intake_intent_classifier.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add backend/app/services/intake_intent_classifier.py backend/tests/test_intake_intent_classifier.py
git commit -m "feat(agent): add intake intent classifier"
```

---

### Task 2: Replace Duplicated Backend Intake Guards

**Files:**
- Modify: `backend/app/services/inline_cards.py`
- Modify: `backend/app/services/llm/tool_validator.py`
- Test: `backend/tests/test_inline_cards_runtime_agenda.py`
- Test: `backend/tests/test_tool_validator.py`

**Step 1: Extend failing tests for shared behavior**

Add assertions that:

```python
assert inline_cards.build_cards(None, 3, "记录刚吃了替普瑞酮")[0]["type"] == "medication_draft"
assert all(card["type"] != "diet_draft" for card in inline_cards.build_cards(None, 3, "删除这一餐"))
```

And keep tool validator tests asserting medication-like `diet.food_items` returns an error.

**Step 2: Verify current behavior**

Run:

```bash
cd backend
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai venv/bin/pytest \
  tests/test_inline_cards_runtime_agenda.py::test_inline_cards_builds_medication_draft_for_medication_intake \
  tests/test_tool_validator.py::TestDietMedicationGuard -q
```

Expected: inline card medication draft test fails until implemented.

**Step 3: Replace duplicated checks**

In `inline_cards.py`:

- import `classify_intake_intent`;
- change `_looks_like_diet_record` to check `classify_intake_intent(q).kind == "diet"`;
- remove local `_looks_like_non_diet_intake`;
- add `_build_medication_draft`.

In `tool_validator.py`:

- import `classify_intake_intent`;
- replace local medication-like diet guard with classifier call;
- remove duplicated marker tuples where no longer needed.

**Step 4: Verify tests pass**

Run:

```bash
cd backend
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai venv/bin/pytest \
  tests/test_intake_intent_classifier.py \
  tests/test_inline_cards_runtime_agenda.py \
  tests/test_tool_validator.py -q
venv/bin/ruff check app/services/intake_intent_classifier.py app/services/inline_cards.py app/services/llm/tool_validator.py tests/test_intake_intent_classifier.py tests/test_inline_cards_runtime_agenda.py tests/test_tool_validator.py
```

Expected: PASS.

**Step 5: Commit**

```bash
git add backend/app/services/intake_intent_classifier.py backend/app/services/inline_cards.py backend/app/services/llm/tool_validator.py backend/tests/test_intake_intent_classifier.py backend/tests/test_inline_cards_runtime_agenda.py backend/tests/test_tool_validator.py
git commit -m "fix(agent): route intake intents through shared classifier"
```

---

### Task 3: Medication Draft Card Contract

**Files:**
- Modify: `backend/app/services/inline_cards.py`
- Modify: `backend/app/services/tool_schema_registry.py`
- Test: `backend/tests/test_inline_cards_runtime_agenda.py`

**Step 1: Write failing card contract test**

```python
def test_inline_cards_builds_medication_draft_for_medication_intake():
    from app.services import inline_cards

    cards = inline_cards.build_cards(db=None, user_id=3, query="记录刚吃了替普瑞酮胶囊（施维舒）")

    card = cards[0]
    assert card["type"] == "medication_draft"
    assert card["data"]["medication_name"] == "替普瑞酮胶囊（施维舒）"
    assert card["data"]["source"] == "chat"
    assert any(action["action"] == "health_record.medication.create" for action in card["actions"])
```

**Step 2: Implement card builder and actions**

Add `_build_medication_draft` and `_medication_draft_actions`:

```python
def _build_medication_draft(db, user_id, q):
    intent = classify_intake_intent(q)
    if intent.kind != "medication":
        return None
    return {
        "medication_name": intent.text,
        "taken_time": intent.slots.get("taken_time"),
        "dose": intent.slots.get("dose"),
        "confidence": intent.confidence,
        "source": "chat",
        "boundary": "确认后记录为已服用; 不替代医嘱, 不调整剂量。",
        "suggestions": ["确认后写入用药记录", "如药名或剂量不准, 请先修改"],
    }
```

Action descriptor:

```python
{
    "id": "confirm-medication-draft",
    "label": "确认已服用",
    "action": "health_record.medication.create",
    "endpoint": "/agent/tool/health_record",
    "requires_manual_confirm": True,
    "payload": {"record_type": "medication", "data": {...}},
    "style": "primary",
}
```

If no safe generic endpoint exists for this action, use route action to `/record?type=medication&...` in Phase 1 and leave server write to the existing chat/tool path.

**Step 3: Verify tests pass**

Run:

```bash
cd backend
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai venv/bin/pytest tests/test_inline_cards_runtime_agenda.py -q
```

Expected: PASS.

**Step 4: Commit**

```bash
git add backend/app/services/inline_cards.py backend/app/services/tool_schema_registry.py backend/tests/test_inline_cards_runtime_agenda.py
git commit -m "feat(chat): add medication draft card"
```

---

### Task 4: Mobile Medication Draft Renderer

**Files:**
- Create: `mobile/components/chat/cards/MedicationDraftCard.tsx`
- Modify: `mobile/components/chat/cards/registry.tsx`
- Test: `mobile/components/chat/cards/__tests__/registry.test.tsx`

**Step 1: Write failing renderer test**

Add to `registry.test.tsx`:

```tsx
it('renders medication draft cards with manual confirm action', () => {
  const rendered = renderCard({
    type: 'medication_draft',
    data: {
      medication_name: '替普瑞酮胶囊（施维舒）',
      confidence: 0.9,
      boundary: '确认后记录为已服用; 不替代医嘱, 不调整剂量。',
    },
    actions: [
      {
        id: 'confirm-medication-draft',
        label: '确认已服用',
        action: 'health_record.medication.create',
        requires_manual_confirm: true,
        style: 'primary',
        payload: { record_type: 'medication', data: { medication_name: '替普瑞酮胶囊（施维舒）' } },
      },
    ],
  });

  expect(rendered).toBeTruthy();
})
```

**Step 2: Implement renderer**

Create a compact card matching diet draft visual language:

- icon: medical/asterisk style
- title: `用药 · 待确认`
- name chip
- confidence/source row
- safety boundary text
- actions rendered by existing registry wrapper

**Step 3: Register card**

Add `medication_draft` to `CARD_RENDERERS` or equivalent registry in `mobile/components/chat/cards/registry.tsx`.

**Step 4: Verify mobile tests**

Run:

```bash
cd mobile
npm test -- components/chat/cards/__tests__/registry.test.tsx --runInBand
npx tsc --noEmit
```

Expected: PASS.

**Step 5: Commit**

```bash
git add mobile/components/chat/cards/MedicationDraftCard.tsx mobile/components/chat/cards/registry.tsx mobile/components/chat/cards/__tests__/registry.test.tsx
git commit -m "feat(mobile-chat): render medication draft cards"
```

---

### Task 5: Release And Verification

**Files:**
- No source changes expected.

**Step 1: Final focused verification**

Run:

```bash
cd backend
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai venv/bin/pytest tests/test_intake_intent_classifier.py tests/test_inline_cards_runtime_agenda.py tests/test_tool_validator.py -q
venv/bin/ruff check app/services/intake_intent_classifier.py app/services/inline_cards.py app/services/llm/tool_validator.py tests/test_intake_intent_classifier.py tests/test_inline_cards_runtime_agenda.py tests/test_tool_validator.py

cd ../mobile
npm test -- components/chat/cards/__tests__/registry.test.tsx --runInBand
npx tsc --noEmit
```

**Step 2: Push**

```bash
git push origin main
```

**Step 3: Backend deploy**

If backend files changed:

```bash
./deploy.sh -b -y
curl -fsS --max-time 10 https://health.executor.life/api/v1/health
```

Expected: health returns `healthy`.

**Step 4: Mobile OTA**

If mobile files changed:

```bash
scripts/mobile-ota.sh production "feat(chat): route intake intents and add medication draft card"
```

Expected: EAS update publishes an iOS update group.

**Step 5: Manual smoke prompts**

In mobile chat:

- "记录午餐吃了牛肉面" -> diet draft card.
- "记录刚吃了替普瑞酮" -> medication draft card, no diet card.
- "吃了鱼油" -> supplement route or no diet card.
- "删除这一餐" -> no diet card.
- "刚吃了一个东西" -> no write card; assistant asks a short clarification.
