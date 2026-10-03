import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { pathToFileURL } from "node:url";

const OSV_BATCH_URL = "https://api.osv.dev/v1/querybatch";
const OSV_VULN_URL = "https://api.osv.dev/v1/vulns/";
const BLOCKING_SEVERITIES = new Set(["HIGH", "CRITICAL", "UNKNOWN"]);
const BATCH_SIZE = 100;

function argumentValue(name, fallback = null) {
  const index = process.argv.indexOf(name);
  if (index < 0) {
    return fallback;
  }
  if (!process.argv[index + 1]) {
    throw new Error(`Missing ${name}`);
  }
  return process.argv[index + 1];
}

function chunked(items, size) {
  const chunks = [];
  for (let index = 0; index < items.length; index += size) {
    chunks.push(items.slice(index, index + size));
  }
  return chunks;
}

function packageNameFromLockPath(lockPath) {
  const marker = "node_modules/";
  const index = lockPath.lastIndexOf(marker);
  if (index < 0) {
    return null;
  }
  const relative = lockPath.slice(index + marker.length);
  const parts = relative.split("/");
  if (parts[0]?.startsWith("@")) {
    return parts.length >= 2 ? `${parts[0]}/${parts[1]}` : null;
  }
  return parts[0] || null;
}

export function buildProductionInventory(lockfile) {
  const packages = lockfile?.packages;
  if (!packages || typeof packages !== "object") {
    throw new Error("package-lock.json is missing packages metadata");
  }
  const inventory = [];
  for (const [lockPath, packageEntry] of Object.entries(packages)) {
    if (!lockPath.includes("node_modules/") || !packageEntry?.version) {
      continue;
    }
    if (packageEntry.dev === true) {
      continue;
    }
    const name = packageEntry.name || packageNameFromLockPath(lockPath);
    if (!name) {
      throw new Error(`Unable to resolve package name from lock path: ${lockPath}`);
    }
    inventory.push({ name, version: String(packageEntry.version), lockPath });
  }
  return inventory.sort((left, right) => (
    left.name.localeCompare(right.name) || left.version.localeCompare(right.version)
    || left.lockPath.localeCompare(right.lockPath)
  ));
}

function parseSeverityValue(value) {
  const severity = String(value ?? "").toUpperCase();
  if (["LOW", "MODERATE", "MEDIUM", "HIGH", "CRITICAL"].includes(severity)) {
    return severity === "MEDIUM" ? "MODERATE" : severity;
  }
  const numeric = Number.parseFloat(severity);
  if (Number.isFinite(numeric)) {
    if (numeric >= 9) return "CRITICAL";
    if (numeric >= 7) return "HIGH";
    if (numeric >= 4) return "MODERATE";
    return "LOW";
  }
  return null;
}

export function classifyOsvSeverity(vulnerability) {
  const databaseSeverity = parseSeverityValue(vulnerability?.database_specific?.severity);
  if (databaseSeverity) {
    return databaseSeverity;
  }
  for (const item of vulnerability?.severity ?? []) {
    const parsed = parseSeverityValue(item?.score);
    if (parsed) {
      return parsed;
    }
  }
  return "UNKNOWN";
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

function hasActiveException({ advisory, packageName, policy, now }) {
  return validatePolicy(policy).some((exception) => (
    exception.advisory === advisory
    && exception.package === packageName
    && now <= new Date(`${exception.expires_on}T23:59:59Z`)
  ));
}

function findingLabel(finding) {
  return `${finding.packageName}@${finding.version}${finding.lockPath ? ` [${finding.lockPath}]` : ""}`;
}

export function evaluateOsvFindings(findings, detailsById, policy = {}, now = new Date()) {
  const blocked = [];
  const allowed = [];
  const ignored = [];

  for (const finding of findings) {
    const details = detailsById.get(finding.id);
    if (!details) {
      blocked.push(`${findingLabel(finding)}: missing OSV details for ${finding.id}`);
      continue;
    }
    const severity = classifyOsvSeverity(details);
    if (!BLOCKING_SEVERITIES.has(severity)) {
      ignored.push(`${findingLabel(finding)}: ${finding.id} (${severity})`);
      continue;
    }
    if (hasActiveException({
      advisory: finding.id,
      packageName: finding.packageName,
      policy,
      now,
    })) {
      allowed.push(`${findingLabel(finding)}: ${finding.id} (${severity})`);
      continue;
    }
    blocked.push(`${findingLabel(finding)}: ${finding.id} (${severity})`);
  }

  return {
    allowed: [...new Set(allowed)].sort(),
    blocked: [...new Set(blocked)].sort(),
    ignored: [...new Set(ignored)].sort(),
  };
}

// This is a reviewed code path, never a policy-provided attestation or command.
export async function evaluateInstalledOsvFindings({
  findings, detailsById, projectRoot, policy = {}, now = new Date(),
}) {
  const remaining = [];
  const verificationFailures = [];
  const verified_backport = [];
  const verified_mitigation = [];
  for (const finding of findings) {
    const details = detailsById.get(finding.id);
    const forge = finding.id === "GHSA-86w9-cpqp-85rv"
      && finding.packageName === "node-forge" && finding.version === "1.4.0";
    const braces = finding.id === "GHSA-vfj7-8cjw-p6xm"
      && finding.packageName === "braces" && finding.version === "3.0.3";
    if ((!forge && !braces) || !details || classifyOsvSeverity(details) !== "HIGH") {
      remaining.push(finding);
      continue;
    }
    try {
      if (!finding.lockPath || !projectRoot) {
        throw new Error("installed package path and project root are required");
      }
      const { verifyInstalledCopy } = forge
        ? await import("./node-forge-backport.cjs")
        : await import("../frontend/scripts/braces-depth-guard.cjs");
      const evidence = verifyInstalledCopy({ projectRoot, lockPath: finding.lockPath });
      if (evidence?.advisory !== finding.id || evidence.package !== finding.packageName
          || evidence.version !== finding.version || evidence.lockPath !== finding.lockPath
          || evidence.behaviorVerified !== true
          || !/^[a-f0-9]{64}$/.test(evidence.sourceSha256 ?? "")) {
        throw new Error("fixed verifier returned invalid evidence");
      }
      (forge ? verified_backport : verified_mitigation).push({ ...finding, severity: "HIGH", ...evidence });
    } catch (error) {
      verificationFailures.push(
        `${findingLabel(finding)}: ${finding.id} (HIGH); backport verification failed: ${error.message}`,
      );
    }
  }
  const result = evaluateOsvFindings(remaining, detailsById, policy, now);
  result.blocked.push(...verificationFailures);
  result.blocked.sort();
  return { ...result, verified_backport, verified_mitigation, findings };
}

async function fetchJson(url, options) {
  const response = await fetch(url, {
    ...options,
    signal: AbortSignal.timeout(120000),
  });
  const text = await response.text();
  if (!response.ok) {
    throw new Error(`${url} returned ${response.status}: ${text.slice(0, 240)}`);
  }
  return JSON.parse(text);
}

export async function queryOsvBatch(inventory) {
  const findings = [];
  for (const batch of chunked(inventory, BATCH_SIZE)) {
    const response = await fetchJson(OSV_BATCH_URL, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        queries: batch.map((item) => ({
          package: { ecosystem: "npm", name: item.name },
          version: item.version,
        })),
      }),
    });
    if (!Array.isArray(response.results) || response.results.length !== batch.length) {
      throw new Error("incomplete OSV batch response");
    }
    for (const [index, result] of response.results.entries()) {
      if (!result || typeof result !== "object" || Array.isArray(result)
          || (result.vulns !== undefined && !Array.isArray(result.vulns))) {
        throw new Error("invalid OSV batch result");
      }
      if (result.next_page_token) {
        throw new Error("incomplete OSV batch: pagination requires a complete audit before passing");
      }
      const dependency = batch[index];
      for (const vulnerability of result?.vulns ?? []) {
        if (!vulnerability?.id) {
          throw new Error(`OSV returned a vulnerability without id for ${dependency.name}`);
        }
        findings.push({
          id: vulnerability.id,
          packageName: dependency.name,
          version: dependency.version,
          lockPath: dependency.lockPath,
        });
      }
    }
  }
  return findings;
}

async function fetchDetails(findings) {
  const details = new Map();
  const ids = [...new Set(findings.map((finding) => finding.id))].sort();
  for (const id of ids) {
    const detail = await fetchJson(`${OSV_VULN_URL}${encodeURIComponent(id)}`, {
      method: "GET",
      headers: { "accept": "application/json" },
    });
    if (detail?.id !== id) throw new Error(`OSV details identity mismatch for ${id}`);
    details.set(id, detail);
  }
  return details;
}

async function main() {
  const lockfilePath = argumentValue("--lockfile", "package-lock.json");
  const policyPath = argumentValue("--policy", null);
  const lockfile = JSON.parse(readFileSync(lockfilePath, "utf8"));
  const policy = policyPath ? JSON.parse(readFileSync(policyPath, "utf8")) : { exceptions: [] };
  const inventory = buildProductionInventory(lockfile);
  const findings = await queryOsvBatch(inventory);
  const details = await fetchDetails(findings);
  const result = await evaluateInstalledOsvFindings({
    findings, detailsById: details, policy, projectRoot: dirname(resolve(lockfilePath)),
  });
  if (result.verified_backport.length > 0) {
    console.log("Verified backports (original advisories retained):");
    for (const item of result.verified_backport) {
      console.log(`- verified_backport: ${findingLabel(item)}: ${item.id} (${item.severity}); source sha256 ${item.sourceSha256}`);
    }
  }

  for (const item of result.verified_mitigation) {
    console.log(`- verified_mitigation: ${findingLabel(item)}: ${item.id} (${item.severity}); source sha256 ${item.sourceSha256}`);
  }
  if (result.blocked.length > 0) {
    console.error("Blocking OSV advisories:");
    for (const item of result.blocked) {
      console.error(`- ${item}`);
    }
    process.exit(1);
  }
  if (result.allowed.length > 0) {
    console.log(`OSV audit passed with ${result.allowed.length} active exception(s).`);
  } else if (result.verified_mitigation.length > 0) {
    console.log(`OSV audit passed with ${result.verified_mitigation.length} verified_mitigation and ${result.verified_backport.length} verified_backport installation(s); original HIGH advisories remain in the report.`);
  } else if (result.verified_backport.length > 0) {
    console.log(`OSV audit passed with ${result.verified_backport.length} verified_backport installation(s); original HIGH advisories remain in the report.`);
  } else {
    console.log(
      `OSV audit passed with no high, critical, or unknown-severity advisories `
      + `across ${inventory.length} production npm package entries.`,
    );
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error) => {
    console.error(`OSV audit gate failed closed: ${error.message}`);
    process.exit(2);
  });
}
