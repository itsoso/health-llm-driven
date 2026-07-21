import { defineConfig, globalIgnores } from 'eslint/config';
import nextCoreWebVitals from 'eslint-config-next/core-web-vitals';

export default defineConfig([
  ...nextCoreWebVitals,
  {
    rules: {
      'react/no-unescaped-entities': 'off',
      'no-console': ['warn', { allow: ['warn', 'error', 'info'] }],

      // eslint-plugin-react-hooks v7 enables React Compiler rules that were not
      // part of this React 18 codebase's previous Next.js lint contract. Keep
      // the established hooks correctness rules while migration work is scoped
      // separately from dependency security updates.
      'react-hooks/immutability': 'off',
      'react-hooks/purity': 'off',
      'react-hooks/refs': 'off',
      'react-hooks/set-state-in-effect': 'off',
      'react-hooks/static-components': 'off',
    },
  },
  globalIgnores(['.next/**', 'out/**', 'build/**', 'next-env.d.ts']),
]);
