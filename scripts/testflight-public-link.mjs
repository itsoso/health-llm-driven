#!/usr/bin/env node
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";

const API_BASE = "https://api.appstoreconnect.apple.com/v1";
const APP_ID = process.env.ASC_APP_ID || "6763569720";
const GROUP_NAME = process.env.TESTFLIGHT_GROUP_NAME || "External Testers";
const LINK_LIMIT = Number(process.env.TESTFLIGHT_PUBLIC_LINK_LIMIT || "10000");
const OUTPUT_DIR = process.env.TESTFLIGHT_OUTPUT_DIR || "artifacts/testflight";

function base64url(input) {
  return Buffer.from(input).toString("base64url");
}

function readPrivateKey() {
  if (process.env.ASC_PRIVATE_KEY_BASE64) {
    return Buffer.from(process.env.ASC_PRIVATE_KEY_BASE64, "base64").toString("utf8");
  }
  if (process.env.ASC_PRIVATE_KEY_PATH) {
    return fs.readFileSync(process.env.ASC_PRIVATE_KEY_PATH, "utf8");
  }
  return "";
}

function makeJwt() {
  const keyId = process.env.ASC_KEY_ID || process.env.APP_STORE_CONNECT_API_KEY;
  const issuerId = process.env.ASC_ISSUER_ID || process.env.APP_STORE_CONNECT_ISSUER_ID;
  const privateKey = readPrivateKey();
  if (!keyId || !issuerId || !privateKey) {
    throw new Error("Missing ASC_KEY_ID, ASC_ISSUER_ID, and ASC_PRIVATE_KEY_PATH or ASC_PRIVATE_KEY_BASE64");
  }

  const header = { alg: "ES256", kid: keyId, typ: "JWT" };
  const payload = {
    iss: issuerId,
    aud: "appstoreconnect-v1",
    exp: Math.floor(Date.now() / 1000) + 20 * 60,
  };
  const signingInput = `${base64url(JSON.stringify(header))}.${base64url(JSON.stringify(payload))}`;
  const signature = crypto.sign("sha256", Buffer.from(signingInput), {
    key: privateKey,
    dsaEncoding: "ieee-p1363",
  });
  return `${signingInput}.${signature.toString("base64url")}`;
}

async function ascFetch(pathname, options = {}) {
  const token = makeJwt();
  const response = await fetch(`${API_BASE}${pathname}`, {
    ...options,
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });
  const text = await response.text();
  const body = text ? JSON.parse(text) : {};
  if (!response.ok) {
    throw new Error(`App Store Connect ${response.status}: ${JSON.stringify(body)}`);
  }
  return body;
}

async function findOrCreateExternalGroup() {
  const query = new URLSearchParams({
    "filter[app]": APP_ID,
    "filter[isInternalGroup]": "false",
    limit: "200",
  });
  const groups = await ascFetch(`/betaGroups?${query.toString()}`);
  const existing = (groups.data || []).find((group) => group.attributes?.name === GROUP_NAME)
    || (groups.data || [])[0];
  if (existing) return existing;

  const created = await ascFetch("/betaGroups", {
    method: "POST",
    body: JSON.stringify({
      data: {
        type: "betaGroups",
        attributes: {
          name: GROUP_NAME,
          publicLinkEnabled: true,
          publicLinkLimitEnabled: true,
          publicLinkLimit: LINK_LIMIT,
        },
        relationships: {
          app: { data: { type: "apps", id: APP_ID } },
        },
      },
    }),
  });
  return created.data;
}

async function enablePublicLink(groupId) {
  const updated = await ascFetch(`/betaGroups/${groupId}`, {
    method: "PATCH",
    body: JSON.stringify({
      data: {
        type: "betaGroups",
        id: groupId,
        attributes: {
          publicLinkEnabled: true,
          publicLinkLimitEnabled: true,
          publicLinkLimit: LINK_LIMIT,
        },
      },
    }),
  });
  return updated.data?.attributes?.publicLink;
}

function writeQrPage(publicLink) {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
  const htmlPath = path.join(OUTPUT_DIR, "index.html");
  const escapedLink = publicLink.replaceAll("&", "&amp;").replaceAll('"', "&quot;");
  const qrSrc = `https://api.qrserver.com/v1/create-qr-code/?size=420x420&data=${encodeURIComponent(publicLink)}`;
  fs.writeFileSync(htmlPath, `<!doctype html>
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
    <p>用 iPhone 扫码安装 TestFlight 测试版。</p>
    <img alt="TestFlight QR code" src="${qrSrc}">
    <p><a href="${escapedLink}">${escapedLink}</a></p>
  </main>
</body>
</html>
`, "utf8");
  return htmlPath;
}

async function main() {
  let publicLink = process.env.TESTFLIGHT_PUBLIC_LINK || "";
  if (!publicLink) {
    const group = await findOrCreateExternalGroup();
    publicLink = group.attributes?.publicLink || await enablePublicLink(group.id);
  }
  if (!publicLink) {
    throw new Error("Public link is not available yet. Ensure the external group has an approved beta build.");
  }
  const htmlPath = writeQrPage(publicLink);
  console.log(publicLink);
  console.log(htmlPath);
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
