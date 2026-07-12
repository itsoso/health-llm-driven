"""DashScope 显式上下文缓存 (Phase-2 rank3) —— 纯 messages 变换, 零 I/O。

背景 (prod prefix-hash 量测, QW4 第0步):
  agent 主循环把 **user 消息留在前部** (index 1), 后续每轮把 assistant(tool_calls) +
  tool 结果 **追加到尾部**, 所以 `_prompt_prefix_signature` 里 `prefix = messages[:last_user]`
  ≈ 只有 system 一条。prod 实测:同一 conversation 内多轮 (sys_hash, prefix_hash) 逐字节
  重复 (qwen 7304 char / Opus 9578-16392 char 的 system 反复重发), 跨 turn 则 sys_hash 发散。
  → 合成轮 (round2) 的墙钟大头是 **重新 prefill 那条 ~7.3k-16k token 的 system**, 而它在
  几秒前的工具决策轮 (round1) 已经原样发过一次。把 system 标成显式缓存断点, round1 写缓存、
  round2 命中, 直接跳过整条 system 的 prefill —— 这是 rank3 的主收益。

DashScope compatible-mode 缓存契约 (help.aliyun.com/zh/model-studio/explicit-cache-guide):
  - Anthropic 式 `cache_control: {"type": "ephemeral"}`, **放在 message content 的 text block 上**,
    content 必须转成数组形 `[{"type": "text", "text": ..., "cache_control": {...}}]`;
  - 每请求最多 **4** 个断点;
  - 每个可缓存前缀 **≥1024 token** (不足会被忽略/拒绝);
  - TTL **5 分钟**, 命中自动续期;
  - 命中按 **10%** 输入价计 (省 ~90%), 首次写入 +25%。
  usage 回传 `usage.prompt_tokens_details.cached_tokens` (openai_provider 已在读)。

标记布局 (**append-only 边界** —— 与 rank12 历史摘要的冻结 checkpoint 契约强绑定):
  1. `mark_system`  (默认开): 末条前导 system 消息尾。缓存 [system]。工具决策轮写、合成轮读
     (同 turn 秒级, 5min 窗内近确定命中);跨 turn 当 system 逐字节相同 (同 sys_hash) 也命中。
     system 恒 >1024 token (7.3k-16k char) → 断点恒有效。**主收益。**
  2. `mark_history_prefix` (默认开): 最后一条 user 之前的最后一条消息尾 (messages[last_user-1])。
     缓存 [system + 之前的会话历史]。多轮长会话线程 (rank12 提到的 6-10k verbatim 历史) 的历史
     前缀命中。仅当该消息存在、与 system 断点不同、且 content 是非空字符串时落点 (否则跳过, 无害)。

  以下两个默认关 (探针实证后由 layout 显式开):
  - `mark_static_preamble`: 把 system 拆成 [静态跨用户前缀 | 其余] 并在前缀尾加断点, 换取跨 turn
    (system 整体发散时) 仍命中静态块。但静态前缀实测 ~918-1278 est token, **贴着 1024 下限**,
    有被端点忽略/拒的风险 → 默认不开, 靠 probe_explicit_cache.py 实证清 1024 且真命中再开。
  - `mark_tail`: 整栈最后一条消息尾, 服务 turn 内 3+ 轮的 append-only 复用。2 轮 turn (工具→合成)
    的合成轮是末轮, 给它写缓存无人复用, 只是白付 +25% 写入 → 默认关, 长链路场景由 probe 决定。

**append-only 契约 (给 rank12 历史摘要):** 上述所有断点都落在 append-only 位置 —— system 是稳定块,
history_prefix 落在「当前 user 之前的历史」尾。未来做历史摘要**必须**把摘要冻结成一个只增不改的
前缀 (checkpoint 只 append、绝不逐轮重摘), 且其边界 ≤ history_prefix 断点;若摘要重写了断点之前的
任何 message, 缓存逐轮失效, 与 rank3 直接互杀 (roadmap rank12 已把此列为硬约束)。

本模块是纯函数 (无 settings / 无网络 / 无 registry), 可单测。gating (flag + ModelEntry
.supports_explicit_cache) 在调用方 (agent_executor, 镜像 thinking_budget 的 fail-closed 门控),
provider 只在拿到显式信号时才调本变换 —— flag 关时 payload 逐字节不变。
"""
from __future__ import annotations

from typing import Any, Dict, List

# DashScope/Anthropic 兼容: ephemeral 断点标记。每次都新建 dict, 不共享可变引用。
CACHE_CONTROL_EPHEMERAL: Dict[str, str] = {"type": "ephemeral"}
# compatible-mode 每请求断点上限。
MAX_CACHE_BREAKPOINTS = 4


def _ephemeral_text_block(text: str) -> Dict[str, Any]:
    """把一段纯文本包成带 ephemeral 断点的 content text block。"""
    return {"type": "text", "text": text, "cache_control": dict(CACHE_CONTROL_EPHEMERAL)}


def _is_markable_string(content: Any) -> bool:
    """content 是可打断点的非空字符串 (数组/None/空串不落点, 保守跳过)。"""
    return isinstance(content, str) and content.strip() != ""


def _last_leading_system_index(messages: List[Dict[str, Any]]) -> int:
    """前导 system 连续段里最后一条的下标 (无则 -1)。

    生产恒是单条 system @ index 0;多条前导 system 时标最后一条 (缓存最长 system 前缀)。
    非前导位置的 system (罕见) 不动 —— 前缀缓存只认从头连续。
    """
    idx = -1
    for i, m in enumerate(messages):
        if m.get("role") == "system":
            idx = i
        else:
            break
    return idx


def _last_user_index(messages: List[Dict[str, Any]]) -> int:
    """最后一条 user 消息下标 (无则 -1) —— 与 _prompt_prefix_signature 同定义。"""
    last = -1
    for i, m in enumerate(messages):
        if m.get("role") == "user":
            last = i
    return last


def apply_cache_markers(
    messages: List[Dict[str, Any]],
    *,
    mark_system: bool = True,
    mark_history_prefix: bool = True,
    mark_tail: bool = False,
) -> List[Dict[str, Any]]:
    """在选定的 append-only 边界上给 messages 打显式缓存断点, 返回**新** list。

    - 绝不原地改传入的 message dict (调用方还要拿 messages 存库 / 做本地状态);只对**落点**
      的 message 造一个新 dict (content 换成带 cache_control 的 text block 数组), 其余 message
      原引用透传 (不复制, 省开销)。
    - 只对 content 为非空字符串的 message 落点;数组形 (多模态 vision) / None (assistant 带
      tool_calls 无正文) 保守跳过, 避免破坏既有 content 结构。
    - 断点数硬顶 MAX_CACHE_BREAKPOINTS;去重 (同一条 message 不重复标)。

    provider 只在 gating 通过 (flag on + 模型 supports_explicit_cache) 时才调本函数 ——
    见 openai_provider._maybe_mark_prompt_cache。
    """
    n = len(messages)
    if n == 0:
        return messages

    # 收集要落点的下标 (去重、按契约优先级)。system 优先 (主收益), 其次 history_prefix, 最后 tail。
    targets: List[int] = []

    sys_idx = _last_leading_system_index(messages) if mark_system else -1
    if sys_idx >= 0 and _is_markable_string(messages[sys_idx].get("content")):
        targets.append(sys_idx)

    if mark_history_prefix:
        last_user = _last_user_index(messages)
        hist_idx = last_user - 1
        if (
            hist_idx >= 0
            and hist_idx not in targets
            and _is_markable_string(messages[hist_idx].get("content"))
        ):
            targets.append(hist_idx)

    if mark_tail:
        tail_idx = n - 1
        if tail_idx not in targets and _is_markable_string(messages[tail_idx].get("content")):
            targets.append(tail_idx)

    if not targets:
        return messages

    # 断点上限: 超了截断 (保留优先级靠前的 system / history_prefix)。
    targets = targets[:MAX_CACHE_BREAKPOINTS]
    target_set = set(targets)

    out: List[Dict[str, Any]] = []
    for i, m in enumerate(messages):
        if i in target_set:
            new_m = dict(m)
            new_m["content"] = [_ephemeral_text_block(m["content"])]
            out.append(new_m)
        else:
            out.append(m)
    return out
