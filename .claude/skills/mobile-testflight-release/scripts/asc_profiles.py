#!/usr/bin/env python3
"""ASC API 助手:用 App Store Connect API Key 非交互地为指定 bundle id 生成 App Store
provisioning profile,绑定到「本机钥匙串里那张分发证书」,下载安装到本地。

EAS 凭据库里的 profile 一旦和当前分发证书漂移(换证书后没重签发),无论 eas build 远端还是
--local 都会一直撞 `doesn't include signing certificate`。本助手绕开 EAS 凭据,直接用 ASC API
(只需 API Key,无 Apple ID / 2FA)把 profile 按本机证书重建。

环境变量:
  APP_STORE_CONNECT_API_KEY   ASC API Key 的 KeyID(如 QWYW6ZVS6C)
  APP_STORE_CONNECT_ISSUER_ID ASC Issuer ID
  .p8 自动取 ~/.appstoreconnect/private_keys/AuthKey_<KeyID>.p8

用法:
  python3 asc_profiles.py <bundleid1> [bundleid2 ...]
  → 为每个 bundle id 建/重建 IOS_APP_STORE profile(名 reva-<hash>),装到
    ~/Library/MobileDevice/Provisioning Profiles/,stdout 打 JSON {bundleid: profile_name}
  需要 pyjwt(`pip install pyjwt cryptography`)。
"""
import base64
import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.error
import urllib.request

import jwt  # pyjwt


def _decode_response(response):
    payload = response.read()
    return json.loads(payload) if payload else None


def _local_dist_cert_serial() -> str:
    """本机钥匙串里 Apple Distribution 证书的序列号(去前导 0,大写)。"""
    pem = subprocess.run(
        ["security", "find-certificate", "-c", "Apple Distribution", "-p"],
        capture_output=True, text=True,
    ).stdout
    out = subprocess.run(
        ["openssl", "x509", "-noout", "-serial"],
        input=pem, capture_output=True, text=True,
    ).stdout.strip()
    # serial=0CD61BFA4... → CD61BFA4...
    return out.split("=", 1)[1].lstrip("0").upper()


def main(bundle_ids):
    key_id = os.environ["APP_STORE_CONNECT_API_KEY"]
    issuer = os.environ["APP_STORE_CONNECT_ISSUER_ID"]
    p8 = open(os.path.expanduser(f"~/.appstoreconnect/private_keys/AuthKey_{key_id}.p8")).read()

    def token():
        return jwt.encode(
            {"iss": issuer, "iat": int(time.time()), "exp": int(time.time()) + 1200,
             "aud": "appstoreconnect-v1"},
            p8, algorithm="ES256", headers={"kid": key_id, "typ": "JWT"},
        )

    def api(path, method="GET", body=None):
        r = urllib.request.Request(
            "https://api.appstoreconnect.apple.com/v1/" + path,
            headers={"Authorization": "Bearer " + token(), "Content-Type": "application/json"},
            method=method, data=json.dumps(body).encode() if body else None,
        )
        try:
            with urllib.request.urlopen(r) as f:
                return f.status, _decode_response(f)
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()[:500]

    # 1) 本机证书序列号 → 匹配 ASC 上的分发证书 id
    want_serial = _local_dist_cert_serial()
    cert_id = None
    for c in api("certificates?filter[certificateType]=DISTRIBUTION&limit=20")[1]["data"]:
        if c["attributes"]["serialNumber"].lstrip("0").upper() == want_serial:
            cert_id = c["id"]
            break
    if not cert_id:
        sys.exit(f"本机分发证书序列号 {want_serial} 在 ASC 上找不到匹配 —— 证书没同步到 Apple?")
    sys.stderr.write(f"本机分发证书 -> ASC cert id {cert_id} (serial {want_serial})\n")

    # 2) bundle id → resource id
    bid_map = {b["attributes"]["identifier"]: b["id"]
               for b in api("bundleIds?limit=200")[1]["data"]}
    existing = {p["attributes"]["name"]: p["id"]
                for p in api("profiles?limit=200")[1]["data"]}
    ppath = pathlib.Path(os.path.expanduser("~/Library/MobileDevice/Provisioning Profiles"))
    ppath.mkdir(parents=True, exist_ok=True)

    out = {}
    for bid in bundle_ids:
        if bid not in bid_map:
            sys.exit(f"bundle id {bid} 在 ASC 上没注册 App ID")
        # 名字稳定且短,基于 bundle id 末段
        nm = "reva-" + bid.split(".")[-1][:20]
        if nm in existing:  # 幂等:删旧重建,确保绑当前证书
            api(f"profiles/{existing[nm]}", "DELETE")
        payload = {"data": {"type": "profiles",
                            "attributes": {"name": nm, "profileType": "IOS_APP_STORE"},
                            "relationships": {
                                "bundleId": {"data": {"type": "bundleIds", "id": bid_map[bid]}},
                                "certificates": {"data": [{"type": "certificates", "id": cert_id}]}}}}
        code, resp = api("profiles", "POST", payload)
        if code not in (200, 201):
            sys.exit(f"创建 profile 失败 {bid}: HTTP {code} {resp}")
        uuid = resp["data"]["attributes"]["uuid"]
        (ppath / f"{uuid}.mobileprovision").write_bytes(
            base64.b64decode(resp["data"]["attributes"]["profileContent"]))
        out[bid] = nm
        sys.stderr.write(f"  ✓ {bid} -> '{nm}' uuid {uuid} installed\n")

    print(json.dumps(out))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("用法: python3 asc_profiles.py <bundleid> [<bundleid> ...]")
    main(sys.argv[1:])
