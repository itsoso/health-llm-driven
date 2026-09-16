const assert = require("node:assert/strict");
const test = require("node:test");
const lockfile = require("../package-lock.json");

test("does not resolve an image-size release affected by the parser loop advisories", () => {
  const resolvedVersions = Object.entries(lockfile.packages)
    .filter(([packagePath]) => packagePath.endsWith("node_modules/image-size"))
    .map(([, metadata]) => metadata.version);

  for (const version of resolvedVersions) {
    const [major, minor, patch] = version.split(".").map(Number);
    const isFixed = major > 2 || (major === 2 && (minor > 0 || patch >= 3));
    assert.equal(isFixed, true, `image-size ${version} is affected by GHSA-w3rx-r6r6-pgpr and GHSA-5p2g-fcmc-qvqq`);
  }
});
