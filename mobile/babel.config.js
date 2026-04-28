/**
 * Babel config — adds module-resolver to translate `@/...` imports
 * at compile time, before Metro's resolver ever sees them.
 *
 * Why: metro.config.js resolver.alias / resolveRequest do not reliably
 * propagate to EAS Linux build env (build #4–6 all failed at JS bundle phase
 * with "Unable to resolve @/lib/queryKeys" despite local success).
 *
 * babel-plugin-module-resolver runs at the AST level, so by the time Metro
 * resolves modules, the `@/foo` strings have already been rewritten to
 * absolute paths. This is environment-independent.
 */
module.exports = function (api) {
  api.cache(true);
  return {
    presets: ['babel-preset-expo'],
    plugins: [
      [
        'module-resolver',
        {
          root: ['./'],
          alias: {
            '@': './',
          },
          extensions: [
            '.ios.ts',
            '.android.ts',
            '.ts',
            '.ios.tsx',
            '.android.tsx',
            '.tsx',
            '.js',
            '.jsx',
            '.json',
          ],
        },
      ],
    ],
  };
};
