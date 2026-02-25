export interface BlindSpotItem {
  id: string
  letter: string
  title: string
  points: string[]
}

export const blindSpotItems: BlindSpotItem[] = [
  {
    id: 'bs-a',
    letter: 'A',
    title: '对手方与「取不出来」风险',
    points: [
      '典型形态：理财/信托/私募/非标「展期」、提前赎回受限、底层穿透不清。',
      '应对：宁可降低收益，也要提高「可取现概率」；按流动性分层。',
    ],
  },
  {
    id: 'bs-b',
    letter: 'B',
    title: '合规穿透与连带责任',
    points: [
      '高管风险不仅是「亏钱」：税务穿透、数据合规、反商业贿赂、关联交易、利益冲突。',
      '应对：按「资产隔离 + 证据链」思路做；CRS 申报一致性为底线。',
    ],
  },
  {
    id: 'bs-c',
    letter: 'C',
    title: '账户风控/误伤导致资金冻结',
    points: [
      '哪怕完全合规，也可能因交易路径复杂而触发风控。',
      '应对：对手方分散（2+2），避免单点依赖。',
    ],
  },
  {
    id: 'bs-d',
    letter: 'D',
    title: '网络安全与精准诈骗',
    points: [
      '高净值、高职位越容易被定制化钓鱼。',
      '应对：硬件 Key、双重验证、重要账号分离、家人反诈演练。',
    ],
  },
  {
    id: 'bs-e',
    letter: 'E',
    title: '健康与家庭结构',
    points: [
      '资产配置若不把重疾概率、家庭照护、继承执行成本算进去，都是纸面收益。',
      '应对：高端医疗险（覆盖海外）、定期寿险；传承与遗嘱提前规划。',
    ],
  },
  {
    id: 'bs-f',
    letter: 'F',
    title: '气候与城市韧性（江浙沪高暴露）',
    points: [
      '极端暴雨内涝、台风、热浪对居住/通勤/医疗的影响，比治安更现实。',
      '应对：第二落点优先选距核心城市 1–2 小时、医疗强、交通强、排涝好的区域。',
    ],
  },
]
