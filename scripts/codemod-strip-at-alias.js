#!/usr/bin/env node
/**
 * Codemod: 把 mobile/ 中所有 `@/foo` 形式的 import 改成相对路径.
 *
 * Usage:
 *   node scripts/codemod-strip-at-alias.js [--dry]
 *
 * 处理: import / require / dynamic import 三种形式.
 * 跳过: __tests__ / node_modules / .next / dist / 二进制.
 */

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..', 'mobile');
const DRY = process.argv.includes('--dry');

const SKIP_DIRS = new Set([
  'node_modules', '.next', 'dist', '.expo', 'ios', 'android',
  'build', '.git', '.cache',
]);

const EXTS = new Set(['.ts', '.tsx', '.js', '.jsx']);

// 跳过 config/build 文件 (它们的 '@/' 是文档/逻辑用的, 不该改)
const SKIP_FILES = new Set([
  'metro.config.js',
  'babel.config.js',
  'app.config.js',
  'eas.json',
  'tsconfig.json',
  'package.json',
]);

function walk(dir, files = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (!SKIP_DIRS.has(entry.name) && !entry.name.startsWith('.')) walk(full, files);
    } else if (EXTS.has(path.extname(entry.name)) && !SKIP_FILES.has(entry.name)) {
      files.push(full);
    }
  }
  return files;
}

function rewriteFile(absFile) {
  const src = fs.readFileSync(absFile, 'utf8');
  if (!src.includes("'@/") && !src.includes('"@/')) return null;

  const dir = path.dirname(absFile);
  let changed = false;

  // 匹配: from '@/x' / from "@/x" / require('@/x') / import('@/x')
  const out = src.replace(/(['"])@\/([^'"]+)\1/g, (full, q, sub) => {
    const target = path.join(ROOT, sub);
    let rel = path.relative(dir, target);
    if (!rel.startsWith('.')) rel = './' + rel;
    changed = true;
    return `${q}${rel}${q}`;
  });

  if (!changed) return null;
  return out;
}

function main() {
  const files = walk(ROOT);
  let touched = 0;
  for (const f of files) {
    const out = rewriteFile(f);
    if (out !== null) {
      touched++;
      if (!DRY) fs.writeFileSync(f, out, 'utf8');
      console.log(`${DRY ? '[dry]' : '[fix]'} ${path.relative(ROOT, f)}`);
    }
  }
  console.log(`\n${touched} files ${DRY ? 'would be' : 'were'} rewritten.`);
}

main();
