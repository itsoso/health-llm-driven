import { execFileSync } from 'node:child_process';
import { describe, expect, it } from 'vitest';

// Exercise Next's App Router React instead of the React 18 in jsdom tests.
describe('workout chart App Router compatibility', () => {
  it('recognizes chart elements with both production bundlers', () => {
    const output = execFileSync(process.execPath, ['-e', `
      const assert = require('node:assert/strict');
      const config = require('./next.config.js');
      const React = require('next/dist/compiled/react');
      const webpack = config.webpack
        ? config.webpack({ resolve: { alias: {} } })
        : { resolve: { alias: {} } };
      const targets = [
        webpack.resolve.alias['react-is'],
        config.turbopack?.resolveAlias?.['react-is'],
      ];
      for (const target of targets) {
        const checker = require(target || 'react-is');
        const chart = React.createElement(function AreaChart() {});
        assert.equal(checker.isElement(chart), true, 'Recharts must recognize App Router chart children');
        assert.equal(checker.isFragment(React.createElement(React.Fragment)), true);
      }
      console.log('recognized');
    `], { cwd: process.cwd(), encoding: 'utf8' });
    expect(output.trim()).toBe('recognized');
  });

  it('renders the heart rate curve and axes using the App Router runtime', () => {
    const output = execFileSync(process.execPath, ['-e', `
      const assert = require('node:assert/strict');
      const Module = require('node:module');
      const original = Module._load;
      const config = require('./next.config.js');
      Module._load = function(id, parent, isMain) {
        if (id === 'react') id = 'next/dist/compiled/react';
        if (id === 'react-dom') id = 'next/dist/compiled/react-dom';
        if (id === 'react-is') id = config.turbopack.resolveAlias['react-is'] || id;
        return original.call(this, id, parent, isMain);
      };
      const React = require('react');
      const { renderToStaticMarkup } = require('next/dist/compiled/react-dom/server');
      const { AreaChart, Area, XAxis, YAxis } = require('recharts');
      const html = renderToStaticMarkup(React.createElement(AreaChart, {
        width: 640, height: 256,
        data: [{ time: 0, hr: 110 }, { time: 1, hr: 130 }],
      }, React.createElement(XAxis, { dataKey: 'time' }),
        React.createElement(YAxis),
        React.createElement(Area, { dataKey: 'hr', isAnimationActive: false })));
      assert.ok(html.includes('recharts-area-curve'), 'heart rate curve must be visible');
      assert.ok(html.includes('recharts-cartesian-axis'), 'chart axes must be visible');
      console.log('rendered');
    `], { cwd: process.cwd(), encoding: 'utf8' });
    expect(output.trim()).toBe('rendered');
  });
});
