export interface SystemDefinition {
  id: number
  name: string
  description: string
  icon: string  // lucide icon name
}

export const systemDefinitions: SystemDefinition[] = [
  {
    id: 1,
    name: '人身安全与家庭韧性',
    description: '72小时应急包、数字安全、家人反诈、证件备份',
    icon: 'Shield',
  },
  {
    id: 2,
    name: '现金流与流动性',
    description: '三层现金水库（T+0/T+7/T+30）、对手方分散',
    icon: 'Banknote',
  },
  {
    id: 3,
    name: '资产结构',
    description: '杠铃策略、核心-卫星架构、全球分散',
    icon: 'PieChart',
  },
  {
    id: 4,
    name: '房产策略',
    description: '自住优先、非核心压缩、降杠杆',
    icon: 'Home',
  },
  {
    id: 5,
    name: '迁移与医疗选择权',
    description: '香港身份、境外账户、合规跨境通道',
    icon: 'Plane',
  },
]
