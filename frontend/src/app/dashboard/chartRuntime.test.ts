import { execFileSync } from 'node:child_process';
import { describe, expect, it } from 'vitest';

// jsdom runs React 18; production App Router uses Next's bundled React.
// Exercise the actual ResponsiveContainer, including its child recognition.
describe('dashboard charts in the App Router runtime', () => {
  for (const bundler of ['webpack', 'turbopack']) {
    it(`renders sleep and steps inside responsive containers with ${bundler}`, () => {
      const output = execFileSync(process.execPath, ['-e', `
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const path = require('node:path');
        const Module = require('node:module');
        const config = require('./next.config.js');
        const target = ${JSON.stringify(bundler)} === 'webpack'
          ? config.webpack?.({ resolve: { alias: {} } }).resolve.alias['react-is']
          : config.turbopack?.resolveAlias?.['react-is'];
        const original = Module._load;
        const records = [
          { record_date: '2026-10-01', sleep_score: 80, steps: 4000 },
          { record_date: '2026-10-02', sleep_score: 85, steps: 5000 },
        ];
        Module._load = function(id, parent, isMain) {
          if (id === 'react') id = 'next/dist/compiled/react';
          if (id === 'react-dom') id = 'next/dist/compiled/react-dom';
          if (id === 'react-is' && !process.env.DASHBOARD_CHART_BASELINE) id = target || id;
          if (id === 'next/navigation') return { useRouter: () => ({ push() {} }) };
          if (id === '@/contexts/AuthContext') return { useAuth: () => ({ user: { id: 77 } }) };
          if (id === '@/components/ProtectedRoute') return { __esModule: true, default: ({ children }) => children };
          if (id === '@/services/api/client') return { api: {} };
          if (id === '@/services/api/health' || id === '@/services/api/devices' || id.includes('blood-pressure/saveFeedback')) return {};
          if (id === '@tanstack/react-query') return {
            useMutation: () => ({}),
            useQuery: ({ queryKey }) => {
              let data = null;
              if (queryKey[0] === 'effective-timezone') data = { timezone: 'Asia/Shanghai' };
              if (queryKey[0] === 'garmin-data') data = records;
              if (queryKey[0] === 'garmin-today') data = [records[1]];
              if (queryKey[0] === 'health-trends-latest') data = { dimensions: [] };
              if (queryKey[0] === 'water-today') data = { total_amount: 1234, target_amount: 2000 };
              if (queryKey[0] === 'diet-today') data = { meals_count: 3, total_calories: 1567 };
              if (queryKey[0] === 'weight-latest') data = [{ weight: 72.5, record_date: '2026-10-02' }];
              return { data: queryKey[0] === 'effective-timezone' ? data : { data }, isSuccess: true, dataUpdatedAt: Date.now() };
            },
          };
          if (id === 'recharts') {
            const lib = original.call(this, id, parent, isMain);
            const React = require('react');
            return { ...lib, ResponsiveContainer: props => React.createElement(lib.ResponsiveContainer,
              { ...props, initialDimension: { width: 640, height: 300 } }) };
          }
          return original.call(this, id, parent, isMain);
        };
        const filename = path.resolve('src/app/dashboard/page.tsx');
        const code = require('esbuild').transformSync(fs.readFileSync(filename, 'utf8'), {
          loader: 'tsx', jsx: 'automatic', jsxImportSource: 'next/dist/compiled/react', format: 'cjs',
        }).code;
        const page = new Module(filename, module);
        page.filename = filename;
        page.paths = Module._nodeModulePaths(path.dirname(filename));
        page._compile(code, filename);
        const { jsx } = require('next/dist/compiled/react/jsx-runtime');
        const { renderToStaticMarkup } = require('next/dist/compiled/react-dom/server');
        const html = renderToStaticMarkup(jsx(page.exports.default, {}));
        assert.ok(html.includes('recharts-line-curve'), 'sleep series must render');
        assert.ok(html.includes('recharts-bar-rectangle'), 'steps series must render');
        assert.equal((html.match(/class="recharts-layer recharts-cartesian-axis /g) || []).length, 4, 'both charts must render both axes');
        assert.ok(html.includes('10-01'), 'date labels must render');
        assert.ok(html.includes('recharts-legend'), 'legends must render');
        for (const label of ['今日饮水', '1234', '今日饮食', '1567 kcal', '最近体重', '72.5']) {
          assert.ok(html.includes(label), label + ' must remain visible alongside Garmin');
        }
        console.log('rendered');
      `], { cwd: process.cwd(), encoding: 'utf8' });
      expect(output.trim()).toBe('rendered');
    });
  }
});
