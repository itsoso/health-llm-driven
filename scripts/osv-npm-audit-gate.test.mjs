import assert from "node:assert/strict";
import test from "node:test";
import * as gate from "./osv-npm-audit-gate.mjs";

import {
  buildProductionInventory,
  classifyOsvSeverity,
  evaluateOsvFindings,
} from "./osv-npm-audit-gate.mjs";

test("buildProductionInventory includes production entries and omits dev-only entries", () => {
  const inventory = buildProductionInventory({
    packages: {
      "": { name: "example" },
      "node_modules/prod": { version: "1.0.0" },
      "node_modules/@scope/prod": { version: "2.0.0" },
      "node_modules/dev-only": { version: "3.0.0", dev: true },
      "node_modules/prod/node_modules/nested": { version: "4.0.0" },
    },
  });

  assert.deepEqual(inventory, [
    { name: "@scope/prod", version: "2.0.0", lockPath: "node_modules/@scope/prod" },
    { name: "nested", version: "4.0.0", lockPath: "node_modules/prod/node_modules/nested" },
    { name: "prod", version: "1.0.0", lockPath: "node_modules/prod" },
  ]);
});

test("classifyOsvSeverity prefers reviewed database severity", () => {
  assert.equal(
    classifyOsvSeverity({ database_specific: { severity: "HIGH" } }),
    "HIGH",
  );
});

test("classifyOsvSeverity falls back to numeric CVSS score", () => {
  assert.equal(
    classifyOsvSeverity({ severity: [{ type: "CVSS_V3", score: "9.1" }] }),
    "CRITICAL",
  );
});

test("classifyOsvSeverity fails closed when severity is missing", () => {
  assert.equal(classifyOsvSeverity({}), "UNKNOWN");
});

test("evaluateOsvFindings blocks high severity advisories", () => {
  const result = evaluateOsvFindings(
    [{ id: "GHSA-high", packageName: "pkg", version: "1.0.0" }],
    new Map([["GHSA-high", { database_specific: { severity: "HIGH" } }]]),
  );

  assert.deepEqual(result.blocked, ["pkg@1.0.0: GHSA-high (HIGH)"]);
});

test("evaluateOsvFindings ignores low severity advisories", () => {
  const result = evaluateOsvFindings(
    [{ id: "GHSA-low", packageName: "pkg", version: "1.0.0" }],
    new Map([["GHSA-low", { database_specific: { severity: "LOW" } }]]),
  );

  assert.deepEqual(result.blocked, []);
  assert.deepEqual(result.ignored, ["pkg@1.0.0: GHSA-low (LOW)"]);
});

test("evaluateOsvFindings allows active explicit exceptions", () => {
  const result = evaluateOsvFindings(
    [{ id: "GHSA-high", packageName: "pkg", version: "1.0.0" }],
    new Map([["GHSA-high", { database_specific: { severity: "HIGH" } }]]),
    {
      exceptions: [{
        advisory: "GHSA-high",
        package: "pkg",
        expires_on: "2099-01-01",
        reason: "test fixture",
      }],
    },
    new Date("2026-01-01T00:00:00Z"),
  );

  assert.deepEqual(result.blocked, []);
  assert.deepEqual(result.allowed, ["pkg@1.0.0: GHSA-high (HIGH)"]);
});


const BACKPORT_ADVISORY = "GHSA-86w9-cpqp-85rv";
const forgeFinding = (lockPath = "node_modules/node-forge") => ({
  id: BACKPORT_ADVISORY, packageName: "node-forge", version: "1.4.0", lockPath,
});
const forgeDetails = new Map([[BACKPORT_ADVISORY, {
  id: BACKPORT_ADVISORY, database_specific: { severity: "HIGH" },
}]]);

test("production inventory retains every duplicate installation and npm alias", () => {
  const inventory = buildProductionInventory({ packages: {
    "node_modules/node-forge": { version: "1.4.0" },
    "node_modules/other/node_modules/node-forge": { version: "1.4.0" },
    "node_modules/forge-alias": { name: "node-forge", version: "1.4.0" },
  }});
  assert.equal(inventory.length, 3);
  assert.equal(new Set(inventory.map((entry) => entry.lockPath)).size, 3);
  assert.ok(inventory.every((entry) => entry.name === "node-forge"));
});

test("pure evaluator does not merge separate vulnerable installations", () => {
  const result = evaluateOsvFindings([
    forgeFinding(), forgeFinding("node_modules/other/node_modules/node-forge"),
  ], forgeDetails);
  assert.equal(result.blocked.length, 2);
  assert.ok(result.blocked.some((entry) => entry.includes("other/node_modules/node-forge")));
});

test("policy declarations cannot attest a backport when the installation is missing", async () => {
  const finding = forgeFinding();
  const result = await gate.evaluateInstalledOsvFindings({
    findings: [finding], detailsById: forgeDetails,
    projectRoot: "/nonexistent-reva-audit-fixture",
    policy: { exceptions: [], verified_backport: [finding],
      verify_command: "must-not-execute" },
  });
  assert.equal(result.blocked.length, 1);
  assert.deepEqual(result.verified_backport, []);
  assert.deepEqual(result.findings, [finding]);
});

test("OSV batch response cannot omit an installation result", async (context) => {
  context.mock.method(globalThis, "fetch", async () => ({
    ok: true, text: async () => JSON.stringify({ results: [{}] }),
  }));
  await assert.rejects(() => gate.queryOsvBatch([
    { name: "node-forge", version: "1.4.0", lockPath: "node_modules/node-forge" },
    { name: "node-forge", version: "1.4.0", lockPath: "node_modules/a/node_modules/node-forge" },
  ]), /incomplete OSV batch/);
});

test("backport eligibility never covers another advisory, version, package, or severity", async () => {
  const cases = [
    { finding: { ...forgeFinding(), id: "GHSA-other" }, severity: "HIGH" },
    { finding: { ...forgeFinding(), version: "1.4.1" }, severity: "HIGH" },
    { finding: { ...forgeFinding(), packageName: "other" }, severity: "HIGH" },
    { finding: forgeFinding(), severity: "CRITICAL" },
    { finding: forgeFinding(), severity: "UNKNOWN" },
  ];
  for (const { finding, severity } of cases) {
    const result = await gate.evaluateInstalledOsvFindings({
      findings: [finding], projectRoot: "/nonexistent-reva-audit-fixture",
      detailsById: new Map([[finding.id, { database_specific: { severity } }]]),
      policy: { exceptions: [], verified_backport: [finding] },
    });
    assert.equal(result.blocked.length, 1);
    assert.deepEqual(result.verified_backport, []);
    assert.ok(!result.blocked[0].includes("backport verification failed"));
  }
});

test("eligible advisory with missing details or missing installation path fails closed", async () => {
  for (const [finding, detailsById] of [
    [forgeFinding(), new Map()],
    [{ ...forgeFinding(), lockPath: undefined }, forgeDetails],
  ]) {
    const result = await gate.evaluateInstalledOsvFindings({
      findings: [finding], detailsById, projectRoot: "/nonexistent-reva-audit-fixture",
    });
    assert.equal(result.blocked.length, 1);
    assert.deepEqual(result.verified_backport, []);
  }
});

test("OSV batch binds each result to its original installed path", async (context) => {
  context.mock.method(globalThis, "fetch", async () => ({
    ok: true, text: async () => JSON.stringify({ results: [
      { vulns: [{ id: BACKPORT_ADVISORY }] }, { vulns: [{ id: BACKPORT_ADVISORY }] },
    ] }),
  }));
  const paths = ["node_modules/node-forge", "node_modules/a/node_modules/node-forge"];
  const findings = await gate.queryOsvBatch(paths.map((lockPath) => ({
    name: "node-forge", version: "1.4.0", lockPath,
  })));
  assert.deepEqual(findings, paths.map(forgeFinding));
});

test("OSV batch rejects malformed individual results", async (context) => {
  for (const result of [null, [], { vulns: {} }, { vulns: [{}] }]) {
    context.mock.method(globalThis, "fetch", async () => ({
      ok: true, text: async () => JSON.stringify({ results: [result] }),
    }));
    await assert.rejects(() => gate.queryOsvBatch([
      { name: "node-forge", version: "1.4.0", lockPath: "node_modules/node-forge" },
    ]));
    context.mock.restoreAll();
  }
});

test("OSV pagination cannot silently omit later advisories", async (context) => {
  context.mock.method(globalThis, "fetch", async () => ({
    ok: true, text: async () => JSON.stringify({ results: [{
      vulns: [{ id: BACKPORT_ADVISORY }], next_page_token: "unread-next-page",
    }] }),
  }));
  await assert.rejects(() => gate.queryOsvBatch([
    { name: "node-forge", version: "1.4.0", lockPath: "node_modules/node-forge" },
  ]), /incomplete OSV batch.*pagination/);
});
