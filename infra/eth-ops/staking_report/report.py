from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class DailyReport:
    report_date: str
    consensus_eth: Decimal | None
    priority_eth: Decimal | None
    mev_eth: Decimal | None
    total_cny: Decimal | None
    health: str
    complete: bool


def _eth(value: Decimal | None) -> str:
    return "未确认" if value is None else f"{value:.8f} ETH"


def render_telegram(report: DailyReport) -> str:
    if report.consensus_eth is None:
        headline = "收益: 基线建立中"
    else:
        known = sum(x for x in (report.consensus_eth, report.priority_eth, report.mev_eth) if x is not None)
        headline = f"已确认收益: {known:.8f} ETH"
    cny = "暂不可用" if report.total_cny is None else f"¥{report.total_cny:.2f}"
    return "\n".join(
        (
            f"ETH 质押日报｜{report.report_date}（北京时间）",
            "",
            headline,
            f"共识层: {_eth(report.consensus_eth)}",
            f"Priority fees: {_eth(report.priority_eth)}",
            f"MEV: {_eth(report.mev_eth)}",
            f"人民币: {cny}",
            f"节点: {report.health}",
            f"数据完整性: {'complete' if report.complete else 'incomplete'}",
        )
    )
