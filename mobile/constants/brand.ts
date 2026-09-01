export const APP_DISPLAY_NAME = '小巴';
export const ASSISTANT_REPLY_NAME = '小巴健康';

// 社交平台品牌色(分享入口图标用)。放在 brand.ts(design token 闸豁免文件)—— 这两个
// 是外部平台官方品牌色,不属 revaTheme 语义色,但组件里裸写 hex 会触发 design:check
// ratchet,故在此收成 token 引用。
export const SOCIAL_BRAND = {
  wechat: '#07C160', // 微信官方绿
  xiaohongshu: '#FF2442', // 小红书官方红
} as const;
