'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const root = path.resolve(process.env.BRACES_TEST_ROOT || 'mobile');
const braces = require(path.join(root, 'node_modules/braces'));
const bounded = error => error instanceof SyntaxError && /maximum nesting depth/.test(error.message);
const nested = (open, close, n) => open.repeat(n) + 'a' + close.repeat(n);

for (const method of ['parse', 'compile', 'expand', 'stringify']) {
  for (const [open, close] of [['{', '}'], ['(', ')'], ['{(', ')}']]) {
    test(`${method} rejects deep ${open} before recursive stack exhaustion`, () => {
      assert.throws(() => braces[method](nested(open, close, open.length === 1 ? 4000 : 2000), { maxDepth: Infinity }), bounded);
    });
  }
  test(`${method} rejects unclosed deep groups`, () => {
    assert.throws(() => braces[method]('{'.repeat(2000) + 'a'), bounded);
  });
}
for (const method of ['compile', 'expand', 'stringify']) {
  test(`${method} rejects direct deep ASTs, including internal module calls`, () => {
    function ast() {
      let node = { type: 'text', value: 'a' };
      for (let i = 0; i < 2000; i++) node = { type: 'root', nodes: [node] };
      return node;
    }
    assert.throws(() => braces[method](ast()), bounded);
    assert.throws(() => require(path.join(root, `node_modules/braces/lib/${method}`))(ast()), bounded);
  });
}
test('public main and create reject too much nesting', () => {
  for (const options of [{}, {expand: true}]) {
    assert.throws(() => braces(nested('{', '}', 2000), options), bounded);
    assert.throws(() => braces.create(nested('(', ')', 2000), options), bounded);
  }
});
test('limit is exact and cannot be disabled through options', () => {
  for (const method of ['compile', 'expand', 'stringify']) {
    assert.doesNotThrow(() => braces[method](nested('(', ')', 100)));
    assert.throws(() => braces[method](nested('(', ')', 101), {maxDepth:false}), bounded);
  }
});
test('ordinary patterns, escaped groups, literals and sequential groups keep semantics', () => {
  assert.equal(braces.compile('src/{a,b}/x'), 'src/(a|b)/x');
  assert.deepEqual(braces.expand('{1..3}'), ['1', '2', '3']);
  assert.deepEqual(braces.expand('a/{b,{c,d}}/e'), ['a/b/e', 'a/c/e', 'a/d/e']);
  assert.equal(braces.stringify('a/{b,c}'), 'a/{b,c}');
  assert.doesNotThrow(() => braces.compile('\\{'.repeat(200)));
  assert.doesNotThrow(() => braces.compile('"' + '{'.repeat(200) + '"'));
  assert.doesNotThrow(() => braces.compile('[' + '{'.repeat(200) + ']'));
  assert.doesNotThrow(() => braces.compile('{a,b}'.repeat(200)));
  assert.equal(braces.compile('a/{b'), 'a/{b');
});
