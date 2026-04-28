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

config.resolver.alias = {
  ...(config.resolver.alias || {}),
  '@': path.resolve(__dirname),
};

module.exports = config;
