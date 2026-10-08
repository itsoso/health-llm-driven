// Requires an installed node-forge 1.4.0 in release-tools or mobile (or NODE_FORGE_TEST_SOURCE).
// No skipped substitute: these tests run the fixed verifier against real package copies.
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { cpSync, mkdirSync, mkdtempSync, readFileSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { evaluateInstalledOsvFindings } from "./osv-npm-audit-gate.mjs";
import backport from "./node-forge-backport.cjs";

const require = createRequire(import.meta.url);
const here = dirname(fileURLToPath(import.meta.url));
const source = process.env.NODE_FORGE_TEST_SOURCE || dirname(require.resolve("node-forge/package.json", {
  paths: [join(here, "release-tools"), join(here, "../mobile")],
}));
const advisory = "GHSA-86w9-cpqp-85rv";
const finding = (lockPath = "node_modules/node-forge") => ({
  id: advisory, packageName: "node-forge", version: "1.4.0", lockPath,
});
const detailsById = new Map([[advisory, { id: advisory, database_specific: { severity: "HIGH" } }]]);

function fixture(t, paths = ["node_modules/node-forge"]) {
  const root = mkdtempSync(join(tmpdir(), "reva-osv-backport-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  for (const lockPath of paths) {
    const destination = join(root, lockPath);
    mkdirSync(dirname(destination), { recursive: true });
    cpSync(source, destination, { recursive: true });
    // Installed CI packages may already be patched. Restore the exact reviewed original fixture.
    const rsa = join(destination, "lib/rsa.js");
    const bytes = readFileSync(rsa);
    if (createHash("sha256").update(bytes).digest("hex") === backport.PIN.sourceSha256) {
      const hunk = readFileSync(join(here, "../mobile/patches/node-forge+1.4.0.patch"), "utf8")
        .split(/^@@.*@@.*\n/m)[1].trimEnd().split("\n");
      const original = hunk.filter((line) => line[0] !== "+").map((line) => line.slice(1)).join("\n") + "\n";
      const patched = hunk.filter((line) => line[0] !== "-").map((line) => line.slice(1)).join("\n") + "\n";
      writeFileSync(rsa, bytes.toString("utf8").replace(patched, original));
    }
    assert.equal(createHash("sha256").update(readFileSync(rsa)).digest("hex"), backport.PIN.originalSha256);
  }
  return root;
}
const evaluate = (projectRoot, findings) => evaluateInstalledOsvFindings({
  projectRoot, findings, detailsById, policy: { exceptions: [] },
});

test("real patched copies each retain a finding and receive verified_backport evidence", async (t) => {
  const paths = ["node_modules/node-forge", "node_modules/other/node_modules/node-forge"];
  const root = fixture(t, paths);
  backport.verifyInstallation({ projectRoot: root, apply: true });
  const findings = paths.map(finding);
  const result = await evaluate(root, findings);
  assert.deepEqual(result.blocked, []);
  assert.deepEqual(result.allowed, []);
  assert.deepEqual(result.findings, findings);
  assert.deepEqual(result.verified_backport.map((item) => item.lockPath), paths);
  assert.ok(result.verified_backport.every((item) => item.behaviorVerified && item.severity === "HIGH"
    && item.sourceSha256 === backport.PIN.sourceSha256));
});

test("audit validates only and never applies the backport", async (t) => {
  const root = fixture(t);
  const rsa = join(root, "node_modules/node-forge/lib/rsa.js");
  const before = readFileSync(rsa);
  const result = await evaluate(root, [finding()]);
  assert.equal(result.blocked.length, 1);
  assert.deepEqual(result.verified_backport, []);
  assert.deepEqual(readFileSync(rsa), before);
});

test("one patched copy cannot attest a second unpatched or absent installation", async (t) => {
  const root = fixture(t);
  backport.verifyInstallation({ projectRoot: root, apply: true });
  const nested = "node_modules/other/node_modules/node-forge";
  const absent = await evaluate(root, [finding(), finding(nested)]);
  assert.equal(absent.blocked.length, 1);
  assert.equal(absent.verified_backport.length, 1);
  const originalRoot = fixture(t);
  mkdirSync(dirname(join(root, nested)), { recursive: true });
  cpSync(join(originalRoot, "node_modules/node-forge"), join(root, nested), { recursive: true });
  const mixed = await evaluate(root, [finding(), finding(nested)]);
  assert.equal(mixed.blocked.length, 1);
  assert.match(mixed.blocked[0], /other\/node_modules\/node-forge/);
  assert.equal(mixed.verified_backport.length, 1);
});

test("source or installed version drift remains blocking even after an earlier successful verification", async (t) => {
  for (const drift of ["lib/rsa.js", "package.json"]) {
    const root = fixture(t);
    backport.verifyInstallation({ projectRoot: root, apply: true });
    assert.equal((await evaluate(root, [finding()])).blocked.length, 0);
    const target = join(root, "node_modules/node-forge", drift);
    if (drift.endsWith(".json")) {
      const metadata = JSON.parse(readFileSync(target, "utf8"));
      metadata.version = "1.4.1";
      writeFileSync(target, JSON.stringify(metadata));
    } else {
      writeFileSync(target, readFileSync(target, "utf8") + "\n// unexpected drift\n");
    }
    const result = await evaluate(root, [finding()]);
    assert.equal(result.blocked.length, 1);
    assert.deepEqual(result.verified_backport, []);
  }
});

test("a symlink to a verified copy outside the project cannot count as a verified installation", async (t) => {
  const external = fixture(t);
  backport.verifyInstallation({ projectRoot: external, apply: true });
  const root = fixture(t, []);
  mkdirSync(join(root, "node_modules"));
  symlinkSync(join(external, "node_modules/node-forge"), join(root, "node_modules/node-forge"), "dir");
  const result = await evaluate(root, [finding()]);
  assert.equal(result.blocked.length, 1);
  assert.deepEqual(result.verified_backport, []);
});


test("another HIGH finding remains blocking beside a verified backport", async (t) => {
  const root = fixture(t);
  backport.verifyInstallation({ projectRoot: root, apply: true });
  const other = { ...finding(), id: "GHSA-other" };
  const details = new Map(detailsById);
  details.set(other.id, { database_specific: { severity: "HIGH" } });
  const result = await evaluateInstalledOsvFindings({
    projectRoot: root, findings: [finding(), other], detailsById: details, policy: { exceptions: [] },
  });
  assert.equal(result.verified_backport.length, 1);
  assert.equal(result.blocked.length, 1);
  assert.match(result.blocked[0], /GHSA-other/);
});

test("CLI reports the retained HIGH finding as verified_backport and does not claim no high advisories", (t) => {
  const root = fixture(t);
  const lock = join(root, "package-lock.json");
  writeFileSync(lock, JSON.stringify({ packages: { "node_modules/node-forge": { version: "1.4.0" } } }));
  const networkFixture = "data:text/javascript," + encodeURIComponent(`
    globalThis.fetch = async (url) => ({ ok: true, text: async () => JSON.stringify(
      url.endsWith("querybatch") ? { results: [{ vulns: [{ id: "${advisory}" }] }] }
      : { id: "${advisory}", database_specific: { severity: "HIGH" } }
    ) });
  `);
  const run = () => spawnSync(process.execPath, ["--import", networkFixture,
    join(here, "osv-npm-audit-gate.mjs"), "--lockfile", lock], { encoding: "utf8", timeout: 30000 });
  const rsa = join(root, "node_modules/node-forge/lib/rsa.js");
  const before = readFileSync(rsa);
  const blocked = run();
  assert.equal(blocked.status, 1, blocked.stderr);
  assert.match(blocked.stderr, /backport verification failed/);
  assert.deepEqual(readFileSync(rsa), before);
  backport.verifyInstallation({ projectRoot: root, apply: true });
  const success = run();
  assert.equal(success.status, 0, success.stderr);
  assert.match(success.stdout, /verified_backport: node-forge@1.4.0 \[node_modules\/node-forge\]/);
  assert.ok(success.stdout.includes(advisory));
  assert.match(success.stdout, /\(HIGH\)/);
  assert.ok(!success.stdout.includes("no high"));
});
