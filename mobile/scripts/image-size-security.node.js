const assert = require("node:assert/strict");
const { spawnSync } = require("node:child_process");
const path = require("node:path");
const test = require("node:test");

const { findBox } = require("image-size/dist/types/utils");

test("rejects zero-sized ISO media boxes before JXL or HEIF parsing", () => {
  const input = Buffer.alloc(8);
  input.write("jxlp", 4, "ascii");

  assert.equal(findBox(input, "jxlp", 0), undefined);
});

test("rejects a zero-length ICNS entry without blocking the event loop", () => {
  const script = `
    const { imageSize } = require("image-size");
    const input = Buffer.alloc(16);
    input.write("icns", 0, "ascii");
    input.writeUInt32BE(16, 4);
    input.write("icp4", 8, "ascii");
    input.writeUInt32BE(0, 12);
    try { imageSize(input); } catch (_) { process.exit(0); }
    process.exit(1);
  `;
  const result = spawnSync(process.execPath, ["-e", script], {
    cwd: path.resolve(__dirname, ".."),
    timeout: 1000,
  });

  assert.notEqual(result.error?.code, "ETIMEDOUT");
  assert.equal(result.status, 0);
});
