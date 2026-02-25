export interface BasketDefault {
  id: string
  name: string
  minPercent: number
  maxPercent: number
  purpose: string
}

export const basketDefaults: BasketDefault[] = [
  {
    id: 'survival_cash',
    name: '生存现金桶',
    minPercent: 25,
    maxPercent: 30,
    purpose: '抗通缩/防断裂，覆盖18-24个月家庭开支',
  },
  {
    id: 'global_growth',
    name: '全球增长桶',
    minPercent: 30,
    maxPercent: 40,
    purpose: '对冲单一货币/经济周期，美股宽基等',
  },
  {
    id: 'stable_anchor',
    name: '稳健压舱石',
    minPercent: 20,
    maxPercent: 25,
    purpose: '提供确定性收益，大跌时有钱可补仓',
  },
  {
    id: 'extreme_hedge',
    name: '极端对冲桶',
    minPercent: 5,
    maxPercent: 10,
    purpose: '防信用崩塌/地缘冲突，黄金等',
  },
]
