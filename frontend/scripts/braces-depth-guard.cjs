'use strict';
// Local mitigation for GHSA-vfj7-8cjw-p6xm, not an upstream fixed release.
// Hard caps include mixed groups and direct AST calls. Options cannot disable them.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const PIN = Object.freeze({advisory: 'GHSA-vfj7-8cjw-p6xm', version: '3.0.3'});
const MANIFEST = {
  "changes": {
    "lib/compile.js": {
      "original": "dc98f22eee3d511785d92a00758d5f0d48efed5f5813bdecc2de430c529b5c9f",
      "patched": "d035073f3170ffc312b6bdee3320d52f387ee98c6fd506e9b063df42beb9bb6c",
      "replacements": [
        [
          "  const walk = (node, parent = {}) => {",
          "  const walk = (node, parent = {}, depth = 0) => {\n    if (depth > 101) throw new SyntaxError('braces exceeds maximum nesting depth (100)');"
        ],
        [
          "walk(child, node)",
          "walk(child, node, depth + 1)"
        ]
      ]
    },
    "lib/expand.js": {
      "original": "41ccc196ebfa7b7781a634e721eb744e4e7bcb54cba427a7e3d6806a1b9e58f7",
      "patched": "57f55444ca0ef01c5119a3c43d45fa9491ebe2176b6aa061502c569ecba9df99",
      "replacements": [
        [
          "  const walk = (node, parent = {}) => {",
          "  const walk = (node, parent = {}, depth = 0) => {\n    if (depth > 101) throw new SyntaxError('braces exceeds maximum nesting depth (100)');"
        ],
        [
          "walk(child, node)",
          "walk(child, node, depth + 1)"
        ]
      ]
    },
    "lib/stringify.js": {
      "original": "379f22d77bfa1478341ccd49c5e4267464aabcbba03558bab332aac23fc6f23a",
      "patched": "4c62339e662152ea6492e6c218e8d5fa909cb013941a281fd885e66bdee4c0ae",
      "replacements": [
        [
          "  const stringify = (node, parent = {}) => {",
          "  const stringify = (node, parent = {}, depth = 0) => {\n    if (depth > 101) throw new SyntaxError('braces exceeds maximum nesting depth (100)');"
        ],
        [
          "stringify(child)",
          "stringify(child, {}, depth + 1)"
        ]
      ]
    },
    "lib/parse.js": {
      "original": "e572166565f15fa6ad9865ae49d678218e32aabfd1b3720f6d0d43d39800d310",
      "patched": "7e815cdc92cdd7ac572cc8754d2189622e5c5441639fffe93d3c59b56bce1e70",
      "replacements": [
        [
          "      stack.push(block);",
          "      if (stack.length > 100) throw new SyntaxError('braces exceeds maximum nesting depth (100)');\n      stack.push(block);"
        ]
      ]
    }
  },
  "unchanged": {
    "index.js": "332ea07c7b006361aad12aa994ca75dc1db8e8382b884909e2f38f10b85c88a4",
    "package.json": "56f08b888a4f30dc7cf8a7dbb36ffe92b737912ba36abe9d069d32167c957ac7",
    "lib/constants.js": "c18ac5adb57308f1ce42a28552da3a31f5d83709743ebd9a636336813a744d4b",
    "lib/utils.js": "b5a7596aa67730412b3c029ef09e84e6b67b8e445cffd35d1d295549c89066c7"
  }
};
const sha = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
function regular(file, directory = false) {
  const stat = fs.lstatSync(file);
  if (stat.isSymbolicLink() || (directory ? !stat.isDirectory() : !stat.isFile() || stat.nlink !== 1)) {
    throw new Error(`Non-regular mitigation path: ${file}`);
  }
}

function checkedLocation(projectRoot, lockPath) {
  const root = fs.realpathSync(projectRoot);
  if (typeof lockPath !== 'string' || lockPath.includes('\\') || path.posix.normalize(lockPath) !== lockPath
      || !/^node_modules\/(?:(?:@[^/]+\/)?[^/]+\/node_modules\/)*braces$/.test(lockPath)
      || lockPath.split('/').some((part) => part === '..' || part === '.')) {
    throw new Error('Invalid braces lock path');
  }
  let location = root;
  for (const part of lockPath.split('/')) {
    location = path.join(location, part);
    regular(location, true);
  }
  return location;
}


function inspectCopy(projectRoot, lockPath) {
  const packageDir = checkedLocation(projectRoot, lockPath);
  regular(path.join(packageDir, 'lib'), true);
  const expected = [...Object.keys(MANIFEST.changes), ...Object.keys(MANIFEST.unchanged)].sort();
  const actual = ['index.js', 'package.json', ...fs.readdirSync(path.join(packageDir, 'lib')).map(n => 'lib/' + n)].sort();
  assert.deepEqual(actual, expected, 'braces executable file inventory drift');
  const changes = [];
  for (const name of expected) {
    const file = path.join(packageDir, name);
    regular(file);
    const bytes = fs.readFileSync(file);
    const digest = sha(bytes);
    const change = MANIFEST.changes[name];
    if (!change) {
      if (digest !== MANIFEST.unchanged[name]) throw new Error('braces supporting source drift: ' + name);
      continue;
    }
    if (![change.original, change.patched].includes(digest)) throw new Error('braces source drift: ' + name);
    let patched = bytes.toString('utf8');
    if (digest === change.original) {
      for (const [before, after] of change.replacements) patched = patched.split(before).join(after);
      if (sha(patched) !== change.patched) throw new Error('braces fixed mitigation result mismatch');
    }
    changes.push({file, patched, applied: digest === change.patched});
  }
  return {packageDir, changes};
}

function verifyBehavior(packageDir) {
  for (const key of Object.keys(require.cache)) {
    if (key.startsWith(packageDir + path.sep)) delete require.cache[key];
  }
  const braces = require(path.join(packageDir, 'index.js'));
  const bounded = error => error instanceof SyntaxError && /maximum nesting depth/.test(error.message);
  for (const method of ['parse', 'compile', 'expand', 'stringify']) {
    for (const [open, close] of [['{', '}'], ['(', ')']]) {
      assert.throws(() => braces[method](open.repeat(2000) + 'a' + close.repeat(2000)), bounded);
    }
  }
  for (const method of ['compile', 'expand', 'stringify']) {
    let ast = {type: 'text', value: 'a'};
    for (let i = 0; i < 2000; i++) ast = {type: 'root', nodes: [ast]};
    assert.throws(() => braces[method](ast), bounded);
  }
  assert.equal(braces.compile('src/{a,b}'), 'src/(a|b)');
  assert.deepEqual(braces.expand('{1..3}'), ['1', '2', '3']);
  assert.equal(braces.stringify('src/{a,b}'), 'src/{a,b}');
}

function verifyInstalledCopy({projectRoot, lockPath}) {
  const copy = inspectCopy(projectRoot, lockPath);
  if (copy.changes.some(c => !c.applied)) throw new Error('braces mitigation not applied: ' + lockPath);
  verifyBehavior(copy.packageDir);
  return {advisory: PIN.advisory, package: 'braces', version: PIN.version, lockPath,
    sourceSha256: sha(JSON.stringify(MANIFEST)), behaviorVerified: true, mitigation: 'bounded-recursion-100'};
}
function installedCopies(projectRoot) {
  const root = fs.realpathSync(projectRoot);
  const copies = [];
  function packages(modules) {
    regular(modules, true);
    for (const entry of fs.readdirSync(modules, { withFileTypes: true })) {
      if (entry.name.startsWith('.')) continue;
      const candidate = path.join(modules, entry.name);
      // Linked packages could conceal another installed copy; do not skip them.
      if (entry.isSymbolicLink()) throw new Error(`Linked package is not auditable: ${candidate}`);
      if (!entry.isDirectory()) continue;
      if (entry.name.startsWith('@')) { packages(candidate); continue; }
      if (entry.name === 'braces') copies.push(path.relative(root, candidate).split(path.sep).join('/'));
      const nested = path.join(candidate, 'node_modules');
      if (fs.existsSync(nested)) packages(nested);
    }
  }
  packages(path.join(root, 'node_modules'));
  if (copies.length === 0) throw new Error('No installed braces copy to verify');
  return copies.sort();
}


function verifyInstallation({projectRoot, apply = false}) {
  if (typeof apply !== 'boolean') throw new Error('apply must be a boolean');
  const paths = installedCopies(projectRoot);
  // Inspect every copy and every byte before applying any change.
  const copies = paths.map(lockPath => inspectCopy(projectRoot, lockPath));
  if (apply) for (const copy of copies) for (const change of copy.changes) {
    if (!change.applied) fs.writeFileSync(change.file, change.patched, {flag: 'r+'});
  }
  return {copies: paths.map(lockPath => verifyInstalledCopy({projectRoot, lockPath}))};
}
module.exports = {verifyInstalledCopy, verifyInstallation, PIN};
if (require.main === module) {
  try {
    const args = process.argv.slice(2);
    const apply = args.includes('--apply');
    const rest = args.filter(arg => arg !== '--apply');
    if (rest.length !== 2 || rest[0] !== '--root' || args.filter(arg => arg === '--apply').length > 1) {
      throw new Error('Usage: node braces-depth-guard.cjs --root ROOT [--apply]');
    }
    process.stdout.write(JSON.stringify(verifyInstallation({projectRoot: rest[1], apply})) + '\n');
  } catch (error) {
    process.stderr.write('braces mitigation verification failed: ' + error.message + '\n');
    process.exitCode = 1;
  }
}
