"""cadence.py —— 小巴单臂回归 + 分数漂移闸(P6 评测常态化)。

一条命令跑完整回归:
  run_xiaoba(题库全跑) → judge(--facts,不参赛 judge 模型,默认 kimi-k2.6)
  → 按家族聚合(仅 xiaoba 一臂) → 追加一条 {ts, run_id, scores_by_family, overall, errors}
  到 history.jsonl → 与上一条记录逐家族比:任一家族 overall 掉分 > 阈值(默认 0.5)
  → exit 2 并打印掉分家族明细(fail-loud);首次运行(无历史)→ 记录并 exit 0。

设计取舍:
  - 单臂:对比框架本是多臂对照;常态化回归只盯自家(小巴),不拉商用臂,省时省钱。
    复用 run_xiaoba.run_battery + judge.run_judge + aggregate.aggregate,不重实现打分/聚合。
  - 时间戳外部传入(--run-id):绝不用 time.now/Date.now 类当前时钟塞进历史 —— 调度器/CI
    传一个稳定 run-id(如 UTC ISO 或 git sha),使历史可复现、可回填、测试可断言。
  - 凭证全走 env:REVA_EVAL_TOKEN(小巴臂) + TOKENPLAN_API_KEY(judge 走 tokenplan 的 kimi)。
    任一缺失 → exit 2 明示,绝不回退硬编码/静默空跑。
  - fail-loud 漂移闸:掉分 > 阈值 exit 2;runner/judge 出错计入 errors,不假绿。

用法:
  REVA_EVAL_TOKEN=... TOKENPLAN_API_KEY=... \
    python -m evals.comparative.cadence --run-id 2026-07-06T00:00:00Z

退出码:
  0  正常(首跑,或所有家族相对上一条未掉超阈值)
  2  漂移(某家族掉分 > 阈值)/ 缺凭证 / 无有效打分(judge 全失败)
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from evals.comparative.aggregate import aggregate
from evals.comparative.battery import Battery, load_battery
from evals.comparative.common import bearer_headers, eval_base, read_jsonl, write_jsonl
from evals.comparative.judge import run_judge
from evals.comparative.run_xiaoba import real_poster, run_battery

ARM = "xiaoba"
HISTORY_PATH = Path(__file__).with_name("history.jsonl")
DEFAULT_JUDGE_MODEL = "kimi-k2.6"
DEFAULT_DRIFT_THRESHOLD = 0.5

# judge 走 tokenplan 的 kimi;小巴臂走部署 API 的 JWT。两把凭证都必须在 env。
REQUIRED_ENV = ("REVA_EVAL_TOKEN", "TOKENPLAN_API_KEY")

# 注入点:测试用 fake runner / judge,避免真调网/真 LLM。
# runner: (Battery) -> List[transcript-dict]      —— 已含 arm/prompt_id/family/answer/latency_ms/error
# judge_runner: (records, Battery) -> List[score-dict] —— 已含 arm/family/overall/error
Runner = Callable[[Battery], List[Dict[str, Any]]]
JudgeRunner = Callable[[List[Dict[str, Any]], Battery], List[Dict[str, Any]]]


def check_env(env: Optional[Dict[str, str]] = None) -> List[str]:
    """返回缺失的必需 env 变量名列表(空=齐全)。绝不打印值。"""
    src = env if env is not None else os.environ
    return [name for name in REQUIRED_ENV if not (src.get(name) or "").strip()]


def _default_runner() -> Runner:
    """真 runner:对部署小巴跑全题库。凭证已在 check_env 里校验过。"""
    base = eval_base()
    poster = real_poster(base)

    def _run(battery: Battery) -> List[Dict[str, Any]]:
        transcripts = run_battery(battery, poster)
        return [t.to_json() for t in transcripts]

    return _run


def _default_judge_runner(judge_model: str, facts: Optional[str]) -> JudgeRunner:
    """真 judge runner:走 backend LLM provider(judge_model 决定,默认不参赛的 kimi)。"""

    def _run(records: List[Dict[str, Any]], battery: Battery) -> List[Dict[str, Any]]:
        return run_judge(records, battery, judge_model=judge_model, facts=facts)

    return _run


def summarize_run(
    scores: List[Dict[str, Any]],
    transcript_errors: int = 0,
) -> Dict[str, Any]:
    """把 judge 打分聚合成单臂家族快照。

    只吃 xiaoba 一臂(非 xiaoba 的记录忽略,理论上单臂跑不会有)。
    返回 {scores_by_family: {fam: overall}, overall: float|None, errors: {...}}。
    errors 计数:transcript 层(runner 失败)+ judge 层(judge_error/未打上分)。
    """
    xiaoba_scores = [s for s in scores if s.get("arm") == ARM]
    judge_errors = sum(1 for s in xiaoba_scores if s.get("overall") is None or s.get("error"))

    scores_by_family: Dict[str, Optional[float]] = {}
    overall: Optional[float] = None
    if xiaoba_scores:
        agg = aggregate(xiaoba_scores)
        fam_row = agg["families"].get(ARM, {})
        # aggregate 已按家族算好 overall 均分(仅计入 overall 非 None 的记录)
        scores_by_family = dict(fam_row)
        overall = agg["arms"].get(ARM, {}).get("overall")

    return {
        "scores_by_family": scores_by_family,
        "overall": overall,
        "errors": {
            "transcript": int(transcript_errors),
            "judge": int(judge_errors),
            "total": int(transcript_errors) + int(judge_errors),
        },
    }


def detect_drift(
    prev: Optional[Dict[str, Any]],
    current: Dict[str, Any],
    threshold: float,
) -> List[Dict[str, Any]]:
    """逐家族比对上一条记录与当前记录,返回掉分超阈值的家族明细。

    只对**两条记录都有 overall(非 None)**的家族判定 —— 一边缺分不算漂移(无从比较,不假红)。
    掉分定义:prev - current > threshold(严格大于)。首跑(prev=None)返回空。
    """
    if not prev:
        return []
    prev_fam = prev.get("scores_by_family") or {}
    cur_fam = current.get("scores_by_family") or {}
    drifts: List[Dict[str, Any]] = []
    for fam, prev_score in prev_fam.items():
        cur_score = cur_fam.get(fam)
        if prev_score is None or cur_score is None:
            continue
        drop = prev_score - cur_score
        if drop > threshold:
            drifts.append(
                {
                    "family": fam,
                    "prev": round(prev_score, 3),
                    "current": round(cur_score, 3),
                    "drop": round(drop, 3),
                }
            )
    # 掉分最狠的排前面
    drifts.sort(key=lambda d: d["drop"], reverse=True)
    return drifts


def load_history(path: Path) -> List[Dict[str, Any]]:
    """读历史(时间序,追加序)。文件不存在=首跑,返回空。"""
    if not path.exists():
        return []
    return read_jsonl(path)


def append_history(path: Path, record: Dict[str, Any]) -> None:
    """追加一条记录到 history.jsonl(不覆盖既有)。"""
    existing = load_history(path)
    write_jsonl(path, [*existing, record])


def run_cadence(
    run_id: str,
    battery: Battery,
    runner: Runner,
    judge_runner: JudgeRunner,
    history_path: Path,
    threshold: float = DEFAULT_DRIFT_THRESHOLD,
) -> Dict[str, Any]:
    """纯函数核心:跑回归 → 聚合 → 追加历史 → 判漂移。全部依赖注入,测试可完全离线。

    返回 {record, drifts, last, exit_code}。exit_code 由调用方(main)透传给进程。
    """
    transcripts = runner(battery)
    transcript_errors = sum(1 for t in transcripts if t.get("error"))
    scores = judge_runner(transcripts, battery)

    summary = summarize_run(scores, transcript_errors=transcript_errors)
    record = {
        "ts": run_id,  # 外部传入的时间戳/run-id;绝不用当前时钟
        "run_id": run_id,
        "scores_by_family": summary["scores_by_family"],
        "overall": summary["overall"],
        "errors": summary["errors"],
    }

    prev = load_history(history_path)
    last = prev[-1] if prev else None

    # 先落历史(即便漂移也留档,便于回看),再判定漂移
    append_history(history_path, record)

    drifts = detect_drift(last, record, threshold)
    exit_code = 0

    # judge 全失败(无任何有效家族分)也 fail-loud:无从判回归 = 视为失败
    if summary["overall"] is None:
        exit_code = 2
    elif drifts:
        exit_code = 2

    return {"record": record, "drifts": drifts, "last": last, "exit_code": exit_code}


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="cadence", description="小巴单臂回归 + 分数漂移闸(P6 评测常态化)"
    )
    ap.add_argument(
        "--run-id",
        required=True,
        help="本次运行的时间戳/标识(外部传入,勿用当前时钟)。例:UTC ISO 或 git sha。",
    )
    ap.add_argument("--battery", default=None, help="题库路径(默认内置 battery.yaml)")
    ap.add_argument("--judge-model", default=DEFAULT_JUDGE_MODEL, help="judge 模型(必须不参赛)")
    ap.add_argument(
        "--drift-threshold",
        type=float,
        default=DEFAULT_DRIFT_THRESHOLD,
        help="家族 overall 掉分阈值,超过则判漂移 exit 2(默认 0.5)",
    )
    ap.add_argument(
        "--facts",
        default=None,
        help="用户真实数据事实清单文件(评审专用):带数据的小巴引用真数据不算编造。",
    )
    ap.add_argument("--history", default=None, help="历史 JSONL 路径(默认内置 history.jsonl)")
    args = ap.parse_args(argv)

    # 凭证 fail-loud(绝不静默空跑)
    missing = check_env()
    if missing:
        print(
            f"[cadence] 缺必需环境变量: {missing}。凭证必须经 env 提供(绝不入库)。",
            file=sys.stderr,
        )
        return 2

    facts_text: Optional[str] = None
    if args.facts:
        p = Path(args.facts)
        if not p.exists():
            print(f"[cadence] --facts 文件不存在: {args.facts}", file=sys.stderr)
            return 2
        facts_text = p.read_text(encoding="utf-8")
        if not facts_text.strip():
            print(f"[cadence] --facts 文件为空: {args.facts}", file=sys.stderr)
            return 2

    battery = load_battery(Path(args.battery) if args.battery else None)
    history_path = Path(args.history) if args.history else HISTORY_PATH

    # 真 runner/judge:出网 + 真 LLM。凭证已校验。
    _ = bearer_headers()  # 提前触发 token 读取,缺失早抛(check_env 已覆盖,这里双保险)
    runner = _default_runner()
    judge_runner = _default_judge_runner(args.judge_model, facts_text)

    result = run_cadence(
        run_id=args.run_id,
        battery=battery,
        runner=runner,
        judge_runner=judge_runner,
        history_path=history_path,
        threshold=args.drift_threshold,
    )

    rec = result["record"]
    print(
        f"[cadence] run_id={rec['run_id']} overall={rec['overall']} "
        f"errors={rec['errors']} → {history_path}",
        file=sys.stderr,
    )
    print(f"[cadence] 家族分: {rec['scores_by_family']}", file=sys.stderr)

    if rec["overall"] is None:
        print(
            "[cadence] ✗ 无任何有效家族分(judge 全失败或全空回答)—— fail-loud exit 2。",
            file=sys.stderr,
        )
        return 2

    if not result["last"]:
        print("[cadence] 首次运行,无历史可比 —— 已记录基线,exit 0。", file=sys.stderr)
        return 0

    if result["drifts"]:
        print(
            f"[cadence] ✗ 分数漂移!以下家族掉分 > {args.drift_threshold}:",
            file=sys.stderr,
        )
        for d in result["drifts"]:
            print(
                f"    {d['family']}: {d['prev']} → {d['current']} (掉 {d['drop']})",
                file=sys.stderr,
            )
        return 2

    print(
        f"[cadence] ✓ 未见家族掉分 > {args.drift_threshold}(对比上一条 run_id={result['last'].get('run_id')})。",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
