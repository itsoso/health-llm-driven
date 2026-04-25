// https://docs.expo.dev/guides/using-eslint/
const { defineConfig } = require('eslint/config');
const expoConfig = require("eslint-config-expo/flat");

module.exports = defineConfig([
  expoConfig,
  {
    ignores: ["dist/*", ".expo/*", "node_modules/*"],
    rules: {
      // RN 不渲染 HTML, 不需要转义引号/撇号
      "react/no-unescaped-entities": "off",

      // 生产 console.log 污染日志, 但保留 warn/error/info
      "no-console": ["warn", { "allow": ["warn", "error", "info"] }],
    },
  },
  {
    // 测试文件提供 vitest/jest globals
    files: ["**/*.test.ts", "**/*.test.tsx", "**/__tests__/**"],
    languageOptions: {
      globals: {
        describe: "readonly",
        it: "readonly",
        test: "readonly",
        expect: "readonly",
        beforeAll: "readonly",
        afterAll: "readonly",
        beforeEach: "readonly",
        afterEach: "readonly",
        vi: "readonly",
        jest: "readonly",
      },
    },
  },
]);
