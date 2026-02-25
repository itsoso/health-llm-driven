export interface RedLineDefinition {
  id: number
  title: string
  description: string
  target: string
}

export const redLineDefinitions: RedLineDefinition[] = [
  {
    id: 1,
    title: '现金流跑道 ≥ 18–24 个月',
    description: '哪怕收入下降/奖金取消/公司波动，仍能维持现有生活与必要支出 18–24 个月（不靠卖房、不靠高风险融资、不靠"理财到期"）',
    target: '把"能随时拿出来的钱"与"看起来是钱但可能拿不出来的钱"严格分开',
  },
  {
    id: 2,
    title: '迁移与医疗"可用性"而非"可能性"',
    description: '不是"理论上能出国/能去香港"，而是随时能做到：证件有效、资金路径合规可执行、落脚点与医疗通道明确',
    target: '至少形成 1 个香港/境外账户体系 + 1 个家人可执行的出行预案',
  },
  {
    id: 3,
    title: '单点失败不致命',
    description: '任何一个单点出问题（某家银行/券商/理财/信托/某套房/某个币种/某个行业），都不会把你逼进"被迫处置"',
    target: '对手方分散 + 资产分层 + 杠杆约束',
  },
]
