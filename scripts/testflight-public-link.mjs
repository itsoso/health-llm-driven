#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";

const OUTPUT_DIR = process.env.TESTFLIGHT_OUTPUT_DIR || "artifacts/testflight";
const publicLink = process.env.TESTFLIGHT_PUBLIC_LINK || "";

function fail(message) {
  console.error(message);
  process.exit(2);
}

function escapeHtml(value) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll('"', "&quot;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

if (!/^https:\/\/testflight\.apple\.com\/join\/[A-Za-z0-9]+$/.test(publicLink)) {
  fail(
    "TESTFLIGHT_PUBLIC_LINK 必须是 App Store Connect 已人工批准的 " +
      "https://testflight.apple.com/join/... 链接；本工具不会创建测试组或开启公开链接。",
  );
}

fs.mkdirSync(OUTPUT_DIR, { recursive: true, mode: 0o700 });
const htmlPath = path.join(OUTPUT_DIR, "index.html");
const escapedLink = escapeHtml(publicLink);
fs.writeFileSync(
  htmlPath,
  `<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>TestFlight Download</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 0; min-height: 100vh; display: grid; place-items: center; background: #f6f7f9; color: #111827; }
    main { width: min(92vw, 520px); background: white; border: 1px solid #e5e7eb; border-radius: 8px; padding: 28px; text-align: center; box-shadow: 0 12px 34px rgba(15, 23, 42, 0.08); }
    img { width: min(76vw, 360px); height: min(76vw, 360px); }
    a { color: #2563eb; word-break: break-all; }
    p { color: #4b5563; line-height: 1.6; }
  </style>
</head>
<body>
  <main>
    <h1>TestFlight 下载</h1>
    <p>用 iPhone 扫码安装已批准的 TestFlight 测试版。</p>
    <img alt="TestFlight QR code" src="./qr.png">
    <p><a href="${escapedLink}">${escapedLink}</a></p>
  </main>
</body>
</html>
`,
  { encoding: "utf8", mode: 0o600 },
);

console.log(publicLink);
console.log(htmlPath);
