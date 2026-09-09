// EAS 23.2.0 still consumes the pre-v7 default export. Keep ts-deepmerge 8's
// security fix; adapt only that consumer, never the merge algorithm.
const { createHash } = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const { createRequire } = require('node:module');

const ORIGINAL_SHA = 'b61e6791d125d548662d8bd142adde7f2966d58f5bbcdc43346e710d2e02740d';
const BEFORE = 'const ts_deepmerge_1 = tslib_1.__importDefault(require("ts-deepmerge"));';
const AFTER = 'const ts_deepmerge_1 = { default: require("ts-deepmerge").merge };';
const sha = text => createHash('sha256').update(text).digest('hex');

function adaptSource(source) {
  const original = source.includes(AFTER) ? source.replace(AFTER, BEFORE) : source;
  if (sha(original) !== ORIGINAL_SHA || original.split(BEFORE).length !== 2) {
    throw new Error('EAS compatibility patch source drift; review the new vendor code');
  }
  return original.replace(BEFORE, AFTER);
}

function apply() {
  const easPackage = require.resolve('eas-cli/package.json');
  const easRoot = path.dirname(easPackage);
  const easRequire = createRequire(easPackage);
  const mergePackage = path.resolve(path.dirname(easRequire.resolve('ts-deepmerge')), '../package.json');
  if (JSON.parse(fs.readFileSync(easPackage, 'utf8')).version !== '23.2.0'
      || JSON.parse(fs.readFileSync(mergePackage, 'utf8')).version !== '8.0.0') {
    throw new Error('EAS compatibility patch version mismatch');
  }
  const target = path.join(easRoot, 'build/commandUtils/new/projectFiles.js');
  if (!fs.lstatSync(target).isFile() || fs.lstatSync(target).isSymbolicLink()) {
    throw new Error('EAS compatibility patch target must be a regular file');
  }
  const original = fs.readFileSync(target, 'utf8');
  const patched = adaptSource(original);
  if (patched !== original) fs.writeFileSync(target, patched);
  if (fs.readFileSync(target, 'utf8') !== patched) throw new Error('EAS patch verification failed');
  console.log('EAS compatibility patch verified');
}

module.exports = { adaptSource };
if (require.main === module) apply();
