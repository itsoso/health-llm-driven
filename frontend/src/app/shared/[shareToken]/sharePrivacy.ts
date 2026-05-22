interface SharedMessageLike {
  role: string;
  content: string;
}

interface SharedConversationLike {
  title: string;
  messages: SharedMessageLike[];
}

const DEFAULT_SITE_BASE_URL = 'https://health.executor.life';
const SENSITIVE_SHARE_DESCRIPTION = '这是一条包含健康敏感信息的用户分享，打开后需确认查看。';

const SENSITIVE_PATTERNS = [
  /基因|遗传|SNP|rs\d+|APOE|ATP7B|CFTR|MTHFR|CYP\d|HLA/u,
  /用药|药物|抗生素|处方|禁用|慎用|剂量|副作用/u,
  /诊断|确诊|肿瘤|癌|阿尔茨海默|糖尿病|高血压|心梗|冠心病/u,
  /体检|化验|检查报告|异常指标|尿铜|铜蓝蛋白|肝功能/u,
  /抑郁|焦虑|精神|心理|睡眠障碍/u,
];

export function publicSiteBaseUrl(rawBase?: string | null): string {
  const candidate = (rawBase || process.env.NEXT_PUBLIC_SITE_BASE_URL || '').trim().replace(/\/$/, '');
  if (!candidate || /localhost|127\.0\.0\.1|0\.0\.0\.0/u.test(candidate)) {
    return DEFAULT_SITE_BASE_URL;
  }
  return candidate;
}

export function isSensitiveSharedConversation(data: SharedConversationLike): boolean {
  const text = `${data.title}\n${data.messages.map(message => message.content).join('\n')}`;
  return SENSITIVE_PATTERNS.some(pattern => pattern.test(text));
}

export function buildSharedMetadata({
  title,
  sensitive,
  firstMessage,
  siteBaseUrl,
}: {
  title: string;
  sensitive: boolean;
  firstMessage?: string | null;
  siteBaseUrl?: string | null;
}) {
  const description = sensitive
    ? SENSITIVE_SHARE_DESCRIPTION
    : (firstMessage?.slice(0, 120) || '来自健康 Agent 的分享');
  return {
    title,
    description,
    imageUrl: `${publicSiteBaseUrl(siteBaseUrl)}/logo-512.png`,
  };
}
