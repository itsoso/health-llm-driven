/**
 * Metro config — explicitly registers `@/` path alias.
 *
 * Why: experiments.tsconfigPaths in app.json doesn't reliably propagate to EAS
 * Linux build env. EAS would fail at "Bundle JavaScript" with
 *   Unable to resolve module @/lib/queryKeys
 * because Metro tried to resolve "@" as a package in node_modules.
 *
 * Explicit resolver.alias is robust across local + EAS environments.
 */
const { getDefaultConfig } = require('expo/metro-config');
const path = require('path');

const config = getDefaultConfig(__dirname);

const projectRoot = path.resolve(__dirname);

// 同时配置 alias + extraNodeModules + custom resolver:
// - alias: 现代 Metro 解析器优先用
// - extraNodeModules: 老版本 fallback
// - resolveRequest: 终极兜底, 显式拦截 '@/...' 重定向到绝对路径
//   (EAS Linux build env 经验: 前两者偶尔被忽略, custom resolver 是最 robust 的解)
config.resolver.alias = {
  ...(config.resolver.alias || {}),
  '@': projectRoot,
};

config.resolver.extraNodeModules = {
  ...(config.resolver.extraNodeModules || {}),
  '@': projectRoot,
};

const originalResolveRequest = config.resolver.resolveRequest;
config.resolver.resolveRequest = (context, moduleName, platform) => {
  if (moduleName.startsWith('@/')) {
    const subPath = moduleName.slice(2); // 去掉 '@/'
    const resolved = path.join(projectRoot, subPath);
    return context.resolveRequest(context, resolved, platform);
  }
  if (originalResolveRequest) {
    return originalResolveRequest(context, moduleName, platform);
  }
  return context.resolveRequest(context, moduleName, platform);
};

module.exports = config;
