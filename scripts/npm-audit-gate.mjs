import { readFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { pathToFileURL } from "node:url";

const BLOCKING_SEVERITIES = new Set(["high", "critical"]);
const EXPIRY_WARNING_MS = 7 * 24 * 60 * 60 * 1000;

function advisoryId(advisory) {
  const url = String(advisory?.url ?? "");
  const fromUrl = url.match(/\/advisories\/([^/?#]+)/i)?.[1];
  return fromUrl || String(advisory?.source ?? "");
}

function validatePolicy(policy) {
  const exceptions = Array.isArray(policy?.exceptions) ? policy.exceptions : [];
  for (const exception of exceptions) {
    if (
      !exception?.advisory
      || !exception?.package
      || !exception?.expires_on
      || !exception?.reason
    ) {
      throw new Error("Every audit exception needs advisory, package, expires_on, and reason");
    }
    if (Number.isNaN(Date.parse(`${exception.expires_on}T23:59:59Z`))) {
      throw new Error(`Invalid audit exception expiry: ${exception.expires_on}`);
    }
  }
  return exceptions;
}

function resolveLeaves(packageName, vulnerabilities, seen = new Set()) {
  if (seen.has(packageName)) {
    return [{ unresolved: `cycle:${packageName}` }];
  }
  const vulnerability = vulnerabilities[packageName];
  if (!vulnerability) {
    return [{ unresolved: `missing:${packageName}` }];
  }
  const nextSeen = new Set(seen);
  nextSeen.add(packageName);
  const leaves = [];
  for (const via of vulnerability.via ?? []) {
    if (typeof via === "string") {
      leaves.push(...resolveLeaves(via, vulnerabilities, nextSeen));
    } else if (via && typeof via === "object") {
      leaves.push(via);
    } else {
      leaves.push({ unresolved: `invalid-via:${packageName}` });
    }
  }
  return leaves.length > 0 ? leaves : [{ unresolved: `no-advisory:${packageName}` }];
}

export function evaluateAuditReport(report, policy, now = new Date()) {
  if (report?.auditReportVersion !== 2 || typeof report?.vulnerabilities !== "object") {
    throw new Error("npm audit did not return a version 2 vulnerability report");
  }
  const exceptions = validatePolicy(policy);
  const vulnerabilities = report.vulnerabilities;
  const allowed = [];
  const blocked = [];
  const warnings = new Set();

  for (const [packageName, vulnerability] of Object.entries(vulnerabilities)) {
    if (!BLOCKING_SEVERITIES.has(vulnerability?.severity)) {
      continue;
    }
    const leaves = resolveLeaves(packageName, vulnerabilities);
    const hasConcreteAdvisory = leaves.some((leaf) => !leaf.unresolved);
    const reasons = [];
    for (const leaf of leaves) {
      if (leaf.unresolved) {
        if (hasConcreteAdvisory && leaf.unresolved.startsWith("cycle:")) {
          continue;
        }
        reasons.push(`unresolved ${leaf.unresolved}`);
        continue;
      }
      const id = advisoryId(leaf);
      const exception = exceptions.find(
        (item) => item.advisory === id && item.package === leaf.name,
      );
      if (!exception) {
        reasons.push(`unapproved ${id || "unknown"} (${leaf.name || packageName})`);
        continue;
      }
      const expiresAt = new Date(`${exception.expires_on}T23:59:59Z`);
      if (now > expiresAt) {
        reasons.push(`expired ${id} on ${exception.expires_on}`);
      } else if (expiresAt.getTime() - now.getTime() <= EXPIRY_WARNING_MS) {
        warnings.add(`${id} (${leaf.name}) expires on ${exception.expires_on}`);
      }
    }
    if (reasons.length > 0) {
      blocked.push(`${packageName}: ${[...new Set(reasons)].join(", ")}`);
    } else {
      allowed.push(packageName);
    }
  }

  return {
    allowed: allowed.sort(),
    blocked: blocked.sort(),
    warnings: [...warnings].sort(),
  };
}

function argumentValue(name) {
  const index = process.argv.indexOf(name);
  if (index < 0 || !process.argv[index + 1]) {
    throw new Error(`Missing ${name}`);
  }
  return process.argv[index + 1];
}

function main() {
  const policyPath = argumentValue("--policy");
  const policy = JSON.parse(readFileSync(policyPath, "utf8"));
  const audit = spawnSync(
    "npm",
    ["audit", "--omit=dev", "--json"],
    { encoding: "utf8", maxBuffer: 20 * 1024 * 1024 },
  );
  if (audit.error) {
    throw audit.error;
  }
  if (audit.status !== 0 && audit.status !== 1) {
    throw new Error(`npm audit process failed with status ${audit.status}`);
  }
  let report;
  try {
    report = JSON.parse(audit.stdout);
  } catch (error) {
    throw new Error(`Unable to parse npm audit JSON: ${error.message}`);
  }
  const result = evaluateAuditReport(report, policy);
  if (result.blocked.length > 0) {
    console.error("Blocking npm advisories:");
    for (const item of result.blocked) {
      console.error(`- ${item}`);
    }
    process.exit(1);
  }
  if (result.warnings.length > 0) {
    console.warn("Npm audit exceptions approaching expiry:");
    for (const item of result.warnings) {
      console.warn(`- ${item}`);
    }
  }
  if (result.allowed.length > 0) {
    console.log(
      `npm audit passed with active, documented advisory exceptions across `
      + `${result.allowed.length} transitive package paths.`,
    );
  } else {
    console.log("npm audit passed with no high or critical advisories.");
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    main();
  } catch (error) {
    console.error(`npm audit gate failed closed: ${error.message}`);
    process.exit(2);
  }
}
