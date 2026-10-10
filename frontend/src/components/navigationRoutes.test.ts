import fs from 'node:fs';
import path from 'node:path';
import ts from 'typescript';
import { expect, it } from 'vitest';

it('every declared navigation URL has a Next.js page', () => {
  const source = ts.createSourceFile('Navigation.tsx', fs.readFileSync(path.resolve('src/components/Navigation.tsx'), 'utf8'), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const routes = new Set<string>();
  const visit = (node: ts.Node) => {
    if (ts.isPropertyAssignment(node) && node.name.getText(source) === 'href' && ts.isStringLiteral(node.initializer)) {
      if (node.initializer.text.startsWith('/')) routes.add(node.initializer.text);
    }
    if (ts.isJsxAttribute(node) && node.name.getText(source) === 'href' && node.initializer && ts.isStringLiteral(node.initializer)) {
      if (node.initializer.text.startsWith('/')) routes.add(node.initializer.text);
    }
    ts.forEachChild(node, visit);
  };
  visit(source);
  expect(routes.size).toBeGreaterThan(30);
  const missing = [...routes].filter(route => !fs.existsSync(path.resolve('src/app', new URL(route, 'https://reva.test').pathname.slice(1), 'page.tsx')));
  expect(missing, `Missing navigation routes: ${missing.join(', ')}`).toEqual([]);
});
