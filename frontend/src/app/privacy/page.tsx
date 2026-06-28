import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: '隐私政策 | 健康助理',
  description: '健康助理如何处理 HealthKit、设备、体检报告、AI 上下文和账号删除请求。',
  robots: { index: true, follow: true },
};

const sections = [
  {
    title: '我们处理哪些数据',
    body: [
      '你主动记录的饮食、运动、症状、睡眠、用药、补剂、体检报告、化验结果和基因报告摘要。',
      '你授权同步的 Apple Health / HealthKit、Apple Watch、Garmin 等设备数据。',
      '账号信息、设备连接状态、提醒设置、AI 对话上下文和必要的审计记录。',
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
      '当你请求 AI 分析或对话时，系统按最小必要原则发送相关上下文。',
      'AI 输出用于解释、总结和生成行动草稿，不能替代医生诊断、治疗、处方或药物剂量调整。',
    ],
  },
  {
    title: '你的控制权',
    body: [
      '你可以在 App 内断开 Apple Health、Garmin 等数据来源，并停止后续同步。',
      '你可以在“我 -> 账号与隐私 -> 删除账号与数据”中发起账号和数据删除请求。',
      '删除请求会进入可审计处理流程，通常 7 天内完成；如需保留法律、风控或安全审计记录，我们会按最小必要原则处理。',
    ],
  },
  {
    title: '医疗边界',
    body: [
      '健康助理提供记录、趋势解读和生活方式建议，不提供诊断、急救分诊、处方、治疗方案或药物剂量调整。',
      '出现胸痛、严重呼吸困难、意识异常、持续高热、严重低血糖等紧急情况时，请立即联系医生或当地急救服务。',
    ],
  },
  {
    title: '联系我们',
    body: [
      '如需行使访问、更正、删除或撤回授权等权利，请在 App 内提交删除请求，或发送邮件至 support@executor.life。',
    ],
  },
];

export default function PrivacyPage() {
  return (
    <main className="min-h-screen bg-slate-50 px-4 py-10 text-slate-900">
      <article className="mx-auto max-w-3xl rounded-2xl border border-slate-200 bg-white p-6 shadow-sm md:p-10">
        <p className="text-sm font-semibold text-teal-700">健康助理 / Reva</p>
        <h1 className="mt-3 text-3xl font-bold tracking-tight text-slate-950">隐私政策</h1>
        <p className="mt-4 text-sm leading-6 text-slate-600">
          最近更新: 2026-06-28。本页面用于 App Store 隐私政策 URL，并与移动端“隐私政策”摘要保持一致。
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
