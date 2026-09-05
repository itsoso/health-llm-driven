import assert from "node:assert/strict";
import test from "node:test";

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
    { name: "@scope/prod", version: "2.0.0" },
    { name: "nested", version: "4.0.0" },
    { name: "prod", version: "1.0.0" },
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
