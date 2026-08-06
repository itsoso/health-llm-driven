import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: '隐私政策 | 小巴',
  description: '小巴如何处理 HealthKit、健康记录、图片、语音音频、位置、AI 上下文和账号删除请求。',
  robots: { index: true, follow: true },
};

const sections = [
  {
    title: '我们处理哪些数据',
    body: [
      '你主动记录的饮食、运动、症状、睡眠、用药、补剂、体检报告、化验结果和基因报告摘要。',
      '你授权同步的 Apple Health / HealthKit、Apple Watch、Garmin 等设备数据。',
      '账号邮箱和用户标识、设备连接状态、提醒设置、AI 对话上下文、你主动上传的图片和语音音频，以及必要的安全与操作审计记录。',
      '仅当你在相关功能中主动授权并使用定位时，我们会读取精确位置，用于查询天气、空气质量和户外活动环境；小巴不持续定位，也不在后台收集位置。',
    ],
  },
  {
    title: 'HealthKit 数据用途',
    body: [
      'HealthKit 数据仅用于健康状态展示、趋势复盘、提醒、个性化健康行动建议和你主动发起的 AI 分析。',
      '我们不会把 HealthKit 或其他健康数据用于广告、营销画像、出售给数据经纪方或与健康管理无关的数据挖掘。',
    ],
  },
  {
    title: 'AI 与第三方模型',
    body: [
      '当你请求 AI 分析或对话时，系统按最小必要原则向完成该次任务所需的 AI 模型服务发送相关上下文；不同模型服务可能位于不同服务区域。',
      '当你主动使用语音输入时，语音音频会通过已认证服务发送给云端语音识别服务以生成文字；音频不用于广告、营销画像或追踪。',
      '模型服务收到的数据只用于完成你请求的对话、识别、总结或建议，不用于第三方广告、营销画像或出售。',
      'AI 输出用于解释、总结和生成行动草稿，不能替代医生诊断、治疗、处方或药物剂量调整。',
    ],
  },
  {
    title: '诊断与性能数据',
    body: [
      '为发现崩溃、卡顿和接口故障，我们会处理必要的崩溃日志、性能数据和客户端事件；生产环境不启用广告跟踪。',
      '客户端事件会与登录账号关联，用于产品交互分析和可靠性改进；崩溃与性能数据默认不与账号健康身份关联。这些数据均不用于广告或营销。',
    ],
  },
  {
    title: '你的控制权',
    body: [
      '你可以在 App 内断开 Apple Health、Garmin 等数据来源，并停止后续同步。',
      '你可以在“我 -> 账号与隐私 -> 删除账号与数据”中发起账号和数据删除请求。',
      '提交后 App 会显示删除请求编号和处理状态；删除请求通常在 7 天内完成。如法律、风控或安全审计要求保留最小必要记录，我们会与业务健康数据分离处理。',
    ],
  },
  {
    title: '医疗边界',
    body: [
      '小巴提供记录、趋势解读和生活方式建议，不提供诊断、急救分诊、处方、治疗方案或药物剂量调整。',
      '出现胸痛、严重呼吸困难、意识异常、持续高热、严重低血糖等紧急情况时，请立即联系医生或当地急救服务。',
    ],
  },
  {
    title: '联系我们',
    body: [
      '小巴由睿为健康运营。如需行使访问、更正、删除或撤回授权等权利，请在 App 内提交删除请求，或发送邮件至 support@executor.life。',
    ],
  },
];

export default function PrivacyPage() {
  return (
    <main className="min-h-screen bg-slate-50 px-4 py-10 text-slate-900">
      <article className="mx-auto max-w-3xl rounded-2xl border border-slate-200 bg-white p-6 shadow-sm md:p-10">
        <p className="text-sm font-semibold text-teal-700">小巴 / 睿为健康</p>
        <h1 className="mt-3 text-3xl font-bold tracking-tight text-slate-950">隐私政策</h1>
        <p className="mt-4 text-sm leading-6 text-slate-600">
          生效及最近更新日期: 2026-08-05。本页面与移动端隐私政策及 App Store 隐私标签保持一致。
        </p>

        <div className="mt-8 space-y-7">
          {sections.map(section => (
            <section key={section.title}>
              <h2 className="text-lg font-bold text-slate-950">{section.title}</h2>
              <ul className="mt-3 space-y-2 text-sm leading-6 text-slate-700">
                {section.body.map(item => (
                  <li key={item} className="flex gap-2">
                    <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-teal-600" />
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      </article>
    </main>
  );
}
