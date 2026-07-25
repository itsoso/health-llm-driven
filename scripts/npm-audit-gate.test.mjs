import assert from "node:assert/strict";
import test from "node:test";

import { evaluateAuditReport } from "./npm-audit-gate.mjs";

const allowedPolicy = {
  exceptions: [
    {
      advisory: "GHSA-mh99-v99m-4gvg",
      package: "brace-expansion",
      expires_on: "2026-08-15",
      reason: "Build tooling only while waiting for the React Native upgrade.",
    },
  ],
};

function reportWith(vulnerabilities) {
  return {
    auditReportVersion: 2,
    vulnerabilities,
    metadata: {
      vulnerabilities: {
        high: Object.keys(vulnerabilities).length,
        critical: 0,
      },
    },
  };
}

test("accepts a transitive chain rooted only in an active exception", () => {
  const report = reportWith({
    "brace-expansion": {
      name: "brace-expansion",
      severity: "high",
      via: [
        {
          source: 1124334,
          name: "brace-expansion",
          url: "https://github.com/advisories/GHSA-mh99-v99m-4gvg",
          severity: "high",
        },
      ],
    },
    glob: {
      name: "glob",
      severity: "high",
      via: ["brace-expansion"],
    },
  });

  assert.deepEqual(
    evaluateAuditReport(report, allowedPolicy, new Date("2026-07-25T00:00:00Z")),
    { allowed: ["brace-expansion", "glob"], blocked: [] },
  );
});

test("blocks an unknown high severity advisory", () => {
  const report = reportWith({
    unsafe: {
      name: "unsafe",
      severity: "high",
      via: [
        {
          source: 999,
          name: "unsafe",
          url: "https://github.com/advisories/GHSA-xxxx-yyyy-zzzz",
          severity: "high",
        },
      ],
    },
  });

  const result = evaluateAuditReport(
    report,
    allowedPolicy,
    new Date("2026-07-25T00:00:00Z"),
  );

  assert.deepEqual(result.allowed, []);
  assert.equal(result.blocked.length, 1);
  assert.match(result.blocked[0], /GHSA-xxxx-yyyy-zzzz/);
});

test("blocks an expired exception", () => {
  const report = reportWith({
    "brace-expansion": {
      name: "brace-expansion",
      severity: "high",
      via: [
        {
          source: 1124334,
          name: "brace-expansion",
          url: "https://github.com/advisories/GHSA-mh99-v99m-4gvg",
          severity: "high",
        },
      ],
    },
  });

  const result = evaluateAuditReport(
    report,
    allowedPolicy,
    new Date("2026-08-16T00:00:00Z"),
  );

  assert.equal(result.blocked.length, 1);
  assert.match(result.blocked[0], /expired/);
});

test("blocks unresolved transitive advisories instead of failing open", () => {
  const report = reportWith({
    glob: {
      name: "glob",
      severity: "high",
      via: ["missing-package"],
    },
  });

  const result = evaluateAuditReport(
    report,
    allowedPolicy,
    new Date("2026-07-25T00:00:00Z"),
  );

  assert.equal(result.blocked.length, 1);
  assert.match(result.blocked[0], /unresolved/);
});
