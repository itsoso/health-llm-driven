#!/usr/bin/env node
/**
 * 复元 Reva 设计 token 强制闸(mobile 版 check_doc_drift）。
 *
 * 为什么:设计系统("复元 Reva" tokens in constants/revaTheme.ts）只有被**每一处**
 * 渲染贯彻,才产生一线 App 的高级感。规范文档不产生约束——**闸才产生约束**。
 * 本脚本扫 components/ + app/,统计**绕过 token**的两类漂移,用 ratchet(只减不增)
 * 守住:存量债 grandfather 进 BASELINE,新增违规 → CI 红(与 §"加层不减层/只 TIGHTEN"
 * 同构)。屏迁到原语后,把 BASELINE 调低,永不回头。
 *
 * 两类违规:
 *   raw_hex        — 组件里裸写 #RRGGBB 颜色字面量,而非走 revaColors / theme 语义 token
 *   raw_fontFamily — fontFamily 裸写字符串,而非 revaFonts.sans/mono(字型贯彻的漏点）
 *
 * 用法:
 *   node scripts/check_design_tokens.js            # ratchet:超 BASELINE → exit 1
 *   node scripts/check_design_tokens.js --report   # 只报告(warn),永远 exit 0
 *   node scripts/check_design_tokens.js --top       # 额外列出每类 top 违规文件
 *
 * 调基线:迁一批屏到原语后,重跑 --report 拿新计数,把 BASELINE 调低并提交。
 */
'use strict';
const fs = require('fs');
const path = require('path');

// ── ratchet 基线(2026-07-16 首次锚定;只许降,不许升）──────────────────────
const BASELINE = { raw_hex: 599, raw_fontFamily: 67 };

const ROOTS = ['components', 'app'];
// token 真源文件本就该定义 hex / 字型——豁免(它们是"规范"本身,不是"违规"）。
const EXEMPT = new Set([
  'constants/revaTheme.ts', 'constants/theme.ts', 'constants/Colors.ts',
  'constants/brand.ts', 'constants/markdownStyles.ts',
]);
const isExempt = (rel) =>
  EXEMPT.has(rel) || rel.includes('__tests__') || rel.endsWith('.test.tsx') || rel.endsWith('.test.ts');

const RE_HEX = /#[0-9A-Fa-f]{6}\b|#[0-9A-Fa-f]{3}\b/;
const RE_FONTFAMILY = /fontFamily:\s*['"]/;

function walk(dir, out) {
  let entries;
  try { entries = fs.readdirSync(dir, { withFileTypes: true }); } catch { return; }
  for (const e of entries) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) { if (e.name !== 'node_modules') walk(p, out); }
    else if (e.name.endsWith('.tsx') || e.name.endsWith('.ts')) out.push(p);
  }
}

function main() {
  const mode = process.argv.includes('--report') ? 'report' : 'ratchet';
  const showTop = process.argv.includes('--top');
  const mobileRoot = path.resolve(__dirname, '..');

  const files = [];
  for (const r of ROOTS) walk(path.join(mobileRoot, r), files);

  const counts = { raw_hex: 0, raw_fontFamily: 0 };
  const byFile = { raw_hex: {}, raw_fontFamily: {} };

  for (const f of files) {
    const rel = path.relative(mobileRoot, f);
    if (isExempt(rel)) continue;
    const lines = fs.readFileSync(f, 'utf8').split('\n');
    for (const line of lines) {
      if (RE_HEX.test(line)) { counts.raw_hex++; byFile.raw_hex[rel] = (byFile.raw_hex[rel] || 0) + 1; }
      if (RE_FONTFAMILY.test(line) && !/revaFonts/.test(line)) {
        counts.raw_fontFamily++; byFile.raw_fontFamily[rel] = (byFile.raw_fontFamily[rel] || 0) + 1;
      }
    }
  }

  console.log('复元 Reva 设计 token 闸 —', mode === 'report' ? 'REPORT(warn)' : 'RATCHET');
  let failed = false;
  for (const k of Object.keys(BASELINE)) {
    const cur = counts[k], base = BASELINE[k];
    const delta = cur - base;
    const flag = delta > 0 ? '  🔴 +' + delta + ' 超基线' : (delta < 0 ? '  🟢 ' + delta + '(可调低基线）' : '  ✓');
    console.log(`  ${k.padEnd(16)} ${String(cur).padStart(4)} / baseline ${base}${flag}`);
    if (delta > 0) failed = true;
    if (showTop) {
      const top = Object.entries(byFile[k]).sort((a, b) => b[1] - a[1]).slice(0, 8);
      for (const [rel, n] of top) console.log(`        ${String(n).padStart(3)}  ${rel}`);
    }
  }

  if (mode === 'report') { console.log('\n(report 模式:仅告知,exit 0。迁屏后用新计数调低 BASELINE。）'); return; }
  if (failed) {
    console.error('\n🔴 设计 token 漂移超基线:新增了绕过 revaTheme 的裸 hex / fontFamily。');
    console.error('   修法:用 revaColors/theme 语义色 + revaFonts.sans/mono,别裸写。');
    console.error('   (确属既有债搬移、非新增 → 迁完把 BASELINE 一起调低。）');
    process.exit(1);
  }
  console.log('\n✓ 无新增漂移(≤ 基线）。');
}

main();
