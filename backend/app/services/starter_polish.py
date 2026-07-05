"""Starter polish — rules-cast-facts → LLM rewrites → deterministic verify gate.

The home conversation-starter chips are produced deterministically by
`conversation_starters._build_candidates` (21 rule generators). Those templates
are correct but stiff. This module gives an OPTIONAL cosmetic polish pass:

    RULES  →  cast facts  →  LLM rewrites wording  →  verify gate  →  serve

Hard invariants (RULES stay the single source of facts):
  - The LLM ONLY rewrites/synthesizes wording. It never introduces a number,
    entity, or prescriptive instruction that the rule text did not already say.
  - A pure, deterministic `verify_polished` gate rejects anything the LLM
    invented; a rejected item keeps its original rule template text.
  - Fail-safe is ALWAYS the rule text: flag off / redis down / provider error /
    parse failure / verify reject → byte-identical to today's rule behavior.

The "anchored set" is self-grounding: any digit/entity present in the template
text is rule-approved, because the rule already emitted it. So verification
anchors output numbers against the JOINED SOURCE TEXTS (not against a separate
facts DB), which is exactly what the rules produced.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Optional, Sequence

logger = logging.getLogger(__name__)

# Redis cache: polished results keyed by user + a hash of the picked signals.
# 6h TTL — long enough to serve repeat visits cheaply, short enough that fresh
# data (new signals → new hash → miss) re-polishes.
_CACHE_TTL_SECONDS = 6 * 60 * 60
# v2: bumped when the persona/system-prompt changed (阿衡→小巴). The persona name
# is NOT part of signals_hash, so without a prefix bump, stale pre-rename polished
# texts (saying 阿衡) could serve up to _CACHE_TTL_SECONDS post-deploy. One-line bump
# invalidates every old entry; future persona changes bump this again.
_CACHE_PREFIX = "starter_polish:v2"


# ── Verify-gate constants ────────────────────────────────────────────────

# Prescriptive-surface denylist: these tokens push a chip from "question about
# your data" toward "medical instruction". They are only allowed through when
# the SOURCE text already contains them (i.e. the rule itself said it).
_RED_WORDS: tuple[str, ...] = (
    "剂量",
    "mg",
    "毫克",
    "微克",
    "停药",
    # 停药同义词 (对抗评审: LLM 更可能写"停掉/停用", 单一词形=假安全)
    "停掉",
    "停用",
    "停服",
    "断药",
    "吃药",
    "加量",
    "减量",
    "换药",
    "服用",
    "每天吃",
    "处方",
    "空腹",
    "断食",
    "禁食",
    "注射",
    "胰岛素",
    "补充",
)

# Bare-imperative advice markers. A polished chip must be a question OR must not
# contain these command-form markers. (The rules phrase everything as questions
# or open prompts; an imperative here means the LLM drifted into giving orders.)
_IMPERATIVE_MARKERS: tuple[str, ...] = ("应该", "必须", "立即去", "马上去", "赶紧")

# Matches a run of digits with optional decimal point / percent, e.g.
# "40", "1.5", "37.2", "150%", "2000". Every such run in the output must appear
# verbatim in the joined source texts.
_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?%?")

# 非阿拉伯数字的"量级"词——数字锚定对它们是空转 (对抗评审实测: "两倍/三分之一"
# 直接放行)。除非源文本本身含有, 一律拒绝。
_WORD_QUANTITIES: tuple[str, ...] = (
    "两倍", "加倍", "翻倍", "翻番", "减半", "一半",
    "三分之一", "三分之二", "四分之一", "大量", "少量", "几次", "多次",
)

# 中文数词 + 临床相关量词的邻接组合 ("三次/五天/两片/一粒"), 同样绕过数字锚定。
_CJK_QTY_RE = re.compile(
    r"[一两二三四五六七八九十百俩半几数][\s]*(?:倍|次|天|周|月|克|片|粒|颗|毫升|小时|分钟|杯|勺|顿|成|份|个小时)"
)

# 合成 chip 的因果连接词——跨信号合成禁止暗示因果 (项目红线: 归因标相关非因果)。
_CAUSAL_CONNECTIVES: tuple[str, ...] = (
    "导致", "引起", "造成", "引发", "使得", "因为", "所以",
)

_MIN_LEN = 6
_MAX_LEN = 40


# ── Public dataclasses ───────────────────────────────────────────────────


@dataclass(frozen=True)
class PolishedCard:
    """A card after the polish pass.

    `text` is the text to SERVE: polished text when it passed the verify gate,
    otherwise the original rule template text. `polished` records which happened
    so callers/logs can eyeball adoption. `key`/`priority` are carried through
    from the source rule card unchanged.

    `synthesis=True` marks the single optional combined item; it has no source
    rule card, so its `key` is "synthesis" and `combines` names the two source
    keys it links.
    """

    key: str
    text: str
    priority: int
    polished: bool
    synthesis: bool = False
    combines: tuple[str, ...] = ()


# ── 1. Cast rule facts ───────────────────────────────────────────────────


def build_polish_input(cards: Sequence[Any]) -> dict:
    """Cast the picked rule cards into the LLM-facing polish input.

    For each card we include {key, template_text, facts} where `facts` is the
    light, self-grounding anchored payload derived FROM THE TEMPLATE TEXT itself
    (numbers/units/metric fragments). Generators return only text, so we do not
    refactor all 21 of them — anything already in the template text is by
    definition rule-approved, which is the exact anchor set the verify gate uses.
    """
    items: list[dict] = []
    for c in cards:
        text = getattr(c, "text", "") or ""
        key = getattr(c, "key", "") or ""
        items.append(
            {
                "key": key,
                "template_text": text,
                "facts": _extract_facts(text),
            }
        )
    return {"cards": items}


def _extract_facts(text: str) -> dict:
    """Derive a light facts payload from template text (numbers + units)."""
    numbers = _NUMBER_RE.findall(text)
    # Common health units/metrics that ride alongside numbers in the templates.
    units = [
        u
        for u in ("ml", "km", "min", "℃", "%", "AQI", "UV", "HRV", "mmHg")
        if u in text
    ]
    return {"numbers": numbers, "units": units}


# ── 2. LLM polish (ONE call, strict JSON contract) ───────────────────────


_TIME_OF_DAY = (
    (5, "清晨"),
    (11, "上午"),
    (13, "中午"),
    (18, "下午"),
    (23, "晚上"),
)


def _time_of_day_label(now) -> str:
    hour = getattr(now, "hour", 12)
    for bound, label in _TIME_OF_DAY:
        if hour < bound:
            return label
    return "深夜"


def _build_messages(cards: Sequence[Any], *, now) -> list[dict]:
    payload = [
        {"key": getattr(c, "key", "") or "", "text": getattr(c, "text", "") or ""}
        for c in cards
    ]
    tod = _time_of_day_label(now)
    system = (
        "你是小巴,一个忠实、温和、具体、善于提问的健康守护者。"
        "你的任务:把给定的每条健康起手提示改写成更自然的一句提问。"
        "严格规则:"
        "① 只改写措辞,绝不新增任何数据、数字、指标、建议或结论;"
        "② 语气温和、具体、问句式(尽量以问号结尾),不命令、不下医嘱;"
        "③ 每条尽量控制在 26 字以内的自然口语提问;"
        "④ 只能引用原文里已经出现的实体和数字,不得引入原文没有的内容。"
        "此外可选:再产出至多一条 synthesis 合并项,把给定的其中两条串成一个自然提问,"
        "但它只能引用那两条原文里出现的实体/数字,不得引入第三方信息。"
    )
    user = (
        f"当前时段:{tod}。\n"
        "下面是需要改写的起手提示(JSON 数组,每条含 key 和 text):\n"
        f"{json.dumps(payload, ensure_ascii=False)}\n\n"
        "请只返回一个 JSON 数组,不要有任何多余文字。数组每一项形如 "
        '{"key": "<原 key>", "text": "<改写后的提问>"}。'
        "如需合并,追加一项 "
        '{"key": "synthesis", "combines": ["<key1>", "<key2>"], "text": "<合并提问>"}。'
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


async def polish_starters(
    cards: Sequence[Any],
    *,
    now,
    provider,
) -> Optional[list[PolishedCard]]:
    """Run ONE polish call, verify each item, return served cards or None.

    Returns None on any failure (empty input, provider error, unparseable LLM
    output) so the caller falls back to pure rule text. Never raises.

    Each source card whose polished text FAILS the verify gate keeps its
    original template text (polished=False). The optional synthesis item is
    included only if it passes the gate against the union of its two sources.
    """
    if not cards:
        return None

    try:
        messages = _build_messages(cards, now=now)
        raw = await provider.chat(
            messages=messages,
            temperature=0.4,
            max_tokens=600,
            stream=False,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[starter_polish] provider chat failed, falling back to rules: %s", exc)
        return None

    text = raw if isinstance(raw, str) else (raw.get("content") if isinstance(raw, dict) else "")
    parsed = _parse_json_array(text or "")
    if parsed is None:
        logger.warning("[starter_polish] LLM output not parseable, falling back to rules")
        return None

    return _assemble_cards(cards, parsed)


def _assemble_cards(cards: Sequence[Any], parsed: list) -> list[PolishedCard]:
    by_key: dict[str, Any] = {}
    for c in cards:
        k = getattr(c, "key", "") or ""
        # First card wins per key (matches rule ordering); keys are unique in
        # practice but guard anyway.
        by_key.setdefault(k, c)
    source_texts = {
        (getattr(c, "key", "") or ""): (getattr(c, "text", "") or "") for c in cards
    }

    # Map LLM rewrites by key; ignore anything referencing an unknown key.
    rewrites: dict[str, str] = {}
    synthesis_item: Optional[dict] = None
    for item in parsed:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "").strip()
        new_text = str(item.get("text") or "").strip()
        if key == "synthesis":
            if synthesis_item is None:  # only the first synthesis is considered
                synthesis_item = item
            continue
        if key in source_texts and new_text:
            rewrites.setdefault(key, new_text)

    out: list[PolishedCard] = []
    for c in cards:
        key = getattr(c, "key", "") or ""
        template = getattr(c, "text", "") or ""
        priority = int(getattr(c, "priority", 0) or 0)
        candidate = rewrites.get(key)
        if candidate and verify_polished(candidate, [template]):
            out.append(PolishedCard(key=key, text=candidate, priority=priority, polished=True))
        else:
            out.append(PolishedCard(key=key, text=template, priority=priority, polished=False))

    # Optional synthesis — verified against the union of its two source texts.
    if synthesis_item is not None:
        syn = _build_synthesis_card(synthesis_item, source_texts, cards)
        if syn is not None:
            out.append(syn)

    return out


def _build_synthesis_card(
    item: dict,
    source_texts: dict[str, str],
    cards: Sequence[Any],
) -> Optional[PolishedCard]:
    combines_raw = item.get("combines")
    new_text = str(item.get("text") or "").strip()
    if not new_text or not isinstance(combines_raw, (list, tuple)):
        return None
    combines = [str(k).strip() for k in combines_raw if str(k).strip()]
    # Must reference exactly-known input keys.
    if len(combines) != 2 or any(k not in source_texts for k in combines):
        return None
    union_sources = [source_texts[k] for k in combines]
    if not verify_polished(new_text, union_sources):
        return None
    # 合成专属: 因果连接词一律拒 (跨信号只许并列陈述, 不许暗示因果 ——
    # 项目红线"归因标相关非因果"; 除非两条源文本本身含有该词)。
    union_joined = " ".join(union_sources)
    if any(c in new_text and c not in union_joined for c in _CAUSAL_CONNECTIVES):
        return None
    # Priority: inherit the max of the two combined source cards so the synthesis
    # slots in near its most salient parent.
    prio = 0
    for c in cards:
        if (getattr(c, "key", "") or "") in combines:
            prio = max(prio, int(getattr(c, "priority", 0) or 0))
    return PolishedCard(
        key="synthesis",
        text=new_text,
        priority=prio,
        polished=True,
        synthesis=True,
        combines=tuple(combines),
    )


# ── 3. Weak-model JSON defense ───────────────────────────────────────────


_CURLY_QUOTE_MAP = {
    "“": '"',  # "
    "”": '"',  # "
    "‘": "'",  # '
    "’": "'",  # '
    "＂": '"',  # ＂ fullwidth quote
}

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)
_ARRAY_RE = re.compile(r"\[.*\]", re.DOTALL)


def _parse_json_array(text: str) -> Optional[list]:
    """Parse a JSON array out of possibly-messy weak-model output.

    Defenses (known lesson: glm/minimax fence output, curly quotes, garbage):
      1. strip ```json ... ``` code fences
      2. normalize curly/fullwidth quotes to ASCII
      3. json.loads; on failure, regex-extract the first [...] and retry
    Returns the list on success, or None on any parse failure (caller falls
    back to rules). Never raises.
    """
    if not text or not text.strip():
        return None
    cleaned = text.strip()

    fence = _FENCE_RE.search(cleaned)
    if fence:
        cleaned = fence.group(1).strip()

    for ch, repl in _CURLY_QUOTE_MAP.items():
        cleaned = cleaned.replace(ch, repl)

    for candidate in (cleaned, _extract_array(cleaned)):
        if candidate is None:
            continue
        try:
            parsed = json.loads(candidate)
        except Exception:  # noqa: BLE001
            continue
        if isinstance(parsed, list):
            return parsed
    return None


def _extract_array(text: str) -> Optional[str]:
    m = _ARRAY_RE.search(text)
    return m.group(0) if m else None


# ── 4. Deterministic verification gate ───────────────────────────────────


def verify_polished(item: str, source_texts: Sequence[str]) -> bool:
    """Return True iff the polished `item` is safe to serve.

    Pure function (no I/O) — unit-tested hard. Rejects anything the LLM invented:

      - length: 6..40 chars after strip (else reject).
      - number anchoring (exact-run): every digit-run in `item` must equal a
        complete digit-run from the sources (set membership, not substring —
        源"165"不为"65"背书).
      - word-quantity anchoring: 两倍/一半/三分之一/大量… and CJK numeral+量词
        (三次/两顿/减三成/半个小时…) rejected unless present in sources.
      - red-word denylist (_RED_WORDS, incl. 停药 synonyms 停掉/停用/停服/断药,
        空腹/断食/注射/胰岛素/微克/补充…) — rejected UNLESS already in sources.
      - imperative markers (应该/必须/立即去/马上去/赶紧) rejected regardless of
        question form (问号不豁免), unless present in sources.
      - (synthesis-only, in _build_synthesis_card): causal connectives
        导致/引起/造成/引发/使得/因为/所以 rejected — 跨信号只许并列不许因果.

    `source_texts` is the anchor set — for a single rewrite it's [template]; for
    a synthesis it's the union of the two source templates.
    """
    if not item:
        return False
    stripped = item.strip()

    # length
    if not (_MIN_LEN <= len(stripped) <= _MAX_LEN):
        return False

    joined = " ".join(source_texts or [])

    # number anchoring — exact-run 集合比对而非子串 (对抗评审: 源"165"曾放行
    # 输出"65"; 源"AQI 210"曾放行"21"。数字必须整串一致才算有背书)。
    source_numbers = set(_NUMBER_RE.findall(joined))
    for num in _NUMBER_RE.findall(stripped):
        if num not in source_numbers:
            return False

    # 词量级锚定 — "两倍/三分之一/大量"等对数字锚定不可见, 同样必须有源背书。
    for qty in _WORD_QUANTITIES:
        if qty in stripped and qty not in joined:
            return False
    for m in _CJK_QTY_RE.finditer(stripped):
        if m.group(0) not in joined:
            return False

    # red-word denylist — allowed only if the source already contained it
    for word in _RED_WORDS:
        if word in stripped and word not in joined:
            return False

    # imperative check — 不再被疑问句形豁免 (对抗评审: "要不要停掉…?"句式合规
    # 内容越界; 祈使词无论句式一律拒, 代价只是回落模板)。
    if any(marker in stripped and marker not in joined for marker in _IMPERATIVE_MARKERS):
        return False

    return True


# ── 5. Cache + progressive enhancement ───────────────────────────────────


def signals_hash(cards: Sequence[Any]) -> str:
    """Stable 16-hex-char digest of the picked cards' (key, text) content.

    Deterministic across visits with the same signals (sorted before hashing);
    a data change flips the hash → cache miss → re-polish.
    """
    pairs = sorted(
        f"{getattr(c, 'key', '') or ''}\x1f{getattr(c, 'text', '') or ''}"
        for c in cards
    )
    blob = "\x1e".join(pairs)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _cache_key(user_id: int, sig_hash: str) -> str:
    return f"{_CACHE_PREFIX}:{user_id}:{sig_hash}"


def read_cached_polish(user_id: int, sig_hash: str) -> Optional[list[dict]]:
    """Return the cached polished payload (list of card dicts) or None.

    Never raises; Redis down / miss / decode error → None (caller serves rules).
    """
    try:
        from app.utils.redis_cache import get_redis_client

        client = get_redis_client()
        if client is None:
            return None
        raw = client.get(_cache_key(user_id, sig_hash))
        if not raw:
            return None
        data = json.loads(raw)
        if isinstance(data, list):
            return data
    except Exception as exc:  # noqa: BLE001
        logger.warning("[starter_polish] cache read failed (bypassing): %s", exc)
    return None


def write_cached_polish(user_id: int, sig_hash: str, payload: list[dict]) -> None:
    """Persist the polished payload for 6h. Never raises."""
    try:
        from app.utils.redis_cache import get_redis_client

        client = get_redis_client()
        if client is None:
            return
        client.setex(
            _cache_key(user_id, sig_hash),
            _CACHE_TTL_SECONDS,
            json.dumps(payload, ensure_ascii=False),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[starter_polish] cache write failed (bypassing): %s", exc)


def cards_to_payload(cards: Sequence[PolishedCard]) -> list[dict]:
    """Serialize PolishedCards to the cache/endpoint dict shape."""
    out: list[dict] = []
    for c in cards:
        d = {"key": c.key, "text": c.text, "priority": c.priority, "polished": c.polished}
        if c.synthesis:
            d["synthesis"] = True
            d["combines"] = list(c.combines)
        out.append(d)
    return out


def warm_polish_cache(user_id: int, cards: Sequence[Any], sig_hash: str) -> None:
    """Background entrypoint: polish the given rule cards and write to cache.

    Runs as a FastAPI BackgroundTask (after the response is sent). Creates the
    cheap polish provider from settings, tags LLM usage as `starter_polish`,
    runs polish+verify, and caches the result. All exceptions are logged at
    WARNING and swallowed — this must never propagate to the request.
    """
    import asyncio
    from datetime import datetime
    from zoneinfo import ZoneInfo

    try:
        if not cards:
            return
        from app.config import settings

        if not getattr(settings, "starter_llm_polish_enabled", True):
            return

        from app.services.llm.factory import create_provider_for_model_id
        from app.services.llm.usage_tracker import set_caller

        model_id = getattr(settings, "starter_llm_polish_model_id", "deepseek-v4-flash")
        provider = create_provider_for_model_id(model_id)
        set_caller("starter_polish", user_id)

        now = datetime.now(ZoneInfo("Asia/Shanghai"))
        polished = asyncio.run(polish_starters(cards, now=now, provider=provider))
        if polished is None:
            return
        write_cached_polish(user_id, sig_hash, cards_to_payload(polished))
        logger.info(
            "[starter_polish] warmed cache user=%s hash=%s cards=%d model=%s",
            user_id,
            sig_hash,
            len(polished),
            model_id,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[starter_polish] warm task failed (bypassing): %s", exc)
