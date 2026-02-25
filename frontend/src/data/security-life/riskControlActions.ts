export interface RiskControlAction {
  id: string
  index: number
  title: string
  points: string[]
}

export const riskControlActions: RiskControlAction[] = [
  {
    id: 'rc1',
    index: 1,
    title: '对手方分散（银行/券商至少「2+2」）',
    points: [
      '境内银行至少 2 家、境外（香港）银行至少 1–2 家。',
      '境内券商至少 2 家、境外券商至少 1 家。',
      '核心逻辑：不是怕某家倒，而是怕风控、系统、政策导致单点失效。',
    ],
  },
  {
    id: 'rc2',
    index: 2,
    title: '存款保险与现金拆分',
    points: [
      '最高偿付限额为人民币 50 万元/同一存款人/同一投保机构。',
      '把「50 万/家/人」当操作上限做现金拆分。',
      '存款保险不覆盖理财/信托/资管产品。',
    ],
  },
  {
    id: 'rc3',
    index: 3,
    title: '币种分散要走合规通道',
    points: [
      '年度便利化额度（等值 5 万美元/人/年），强调真实性合规审核。',
      '合规跨境配置提前做，不要风险来临时才开路。',
      '不要走灰色路径，CRS 与税务居民申报一致性为底线。',
    ],
  },
  {
    id: 'rc4',
    index: 4,
    title: '把 AI 参与方式「降维」',
    points: [
      '核心仓：宽基指数（美股/全球）天然包含 AI 龙头。',
      '卫星仓：主题限制在金融资产 5–10%。',
      '绝不做：高杠杆、单票重仓、消息驱动追涨杀跌。',
    ],
  },
]
