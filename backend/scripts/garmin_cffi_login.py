#!/usr/bin/env python3
"""服务器端用 curl_cffi (Chrome TLS) 登录 Garmin 并注入 session"""
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timedelta

def main():
    from curl_cffi.requests import Session as CffiSession
    from sqlalchemy import create_engine, text
    from app.config import settings
    from app.services.auth import GarminCredentialService

    # 读取密码
    e = create_engine(settings.effective_database_url)
    with e.connect() as c:
        row = c.execute(text("SELECT encrypted_password, garmin_email FROM garmin_credentials WHERE user_id=3")).fetchone()

    email = row[1]
    password = GarminCredentialService.decrypt_password(row[0])
    print(f"[1/4] Email: {email}")

    # curl_cffi 登录
    s = CffiSession(impersonate="chrome")
    SSO = "https://sso.garmin.com/sso"

    print("[2/4] GET signin page...")
    r1 = s.get(f"{SSO}/signin", params={"service": "https://connect.garmin.com/modern"})
    print(f"  status={r1.status_code}")

    csrf_match = re.search(r'name="_csrf"\s+value="([^"]+)"', r1.text)
    if not csrf_match:
        print(f"  No CSRF token. Cloudflare challenge: {'challenge' in r1.text.lower()}")
        sys.exit(1)

    print(f"  CSRF: {csrf_match.group(1)[:20]}...")

    print("[3/4] POST login...")
    r2 = s.post(
        f"{SSO}/signin",
        params={"service": "https://connect.garmin.com/modern"},
        data={"username": email, "password": password, "embed": "false", "_csrf": csrf_match.group(1)},
        headers={"Referer": r1.url, "Origin": "https://sso.garmin.com"},
    )
    print(f"  status={r2.status_code}")

    title_match = re.search(r"<title>([^<]+)</title>", r2.text)
    title = title_match.group(1).strip() if title_match else "?"
    print(f"  title={title}")

    ticket_match = re.search(r"ticket=([A-Za-z0-9_\-]+)", r2.text) or re.search(r"ticket=([A-Za-z0-9_\-]+)", str(r2.url))

    if not ticket_match:
        errors = re.findall(r'class="[^"]*error[^"]*"[^>]*>([^<]+)', r2.text)
        for err in errors:
            if err.strip():
                print(f"  Error: {err.strip()}")

        if "MFA" in title or "verification" in title.lower():
            print("  NEEDS MFA - not supported in this script")
        elif "unexpected" in str(errors).lower() or r2.status_code == 429:
            print("  Account likely locked by Garmin. Wait a few hours.")
        sys.exit(1)

    ticket = ticket_match.group(1)
    print(f"  TICKET: {ticket[:30]}...")

    print("[4/4] Exchange for OAuth token...")
    import garth
    from garth.sso import get_oauth1_token, exchange

    for cookie in s.cookies.jar:
        garth.client.sess.cookies.set(cookie.name, cookie.value, domain=cookie.domain, path=cookie.path)

    oauth1 = get_oauth1_token(ticket, garth.client)
    oauth2 = exchange(oauth1, garth.client)
    garth.client.oauth1_token = oauth1
    garth.client.oauth2_token = oauth2
    print(f"  OAuth OK! refresh_token={'YES' if oauth2.refresh_token else 'NO'}")

    # Save + inject
    with tempfile.TemporaryDirectory() as d:
        garth.save(d)
        session_data = {}
        for fname in ["oauth1_token.json", "oauth2_token.json"]:
            fpath = os.path.join(d, fname)
            if os.path.exists(fpath):
                with open(fpath) as f:
                    session_data[fname] = json.load(f)

    session_json = json.dumps(session_data)

    from app.database import SessionLocal
    from app.models.user import GarminCredential
    db = SessionLocal()
    cred = db.query(GarminCredential).filter(GarminCredential.user_id == 3).first()
    cred.garth_session = session_json
    cred.session_expires_at = datetime.utcnow() + timedelta(hours=23)
    cred.login_locked_until = None
    cred.credentials_valid = True
    cred.last_error = None
    cred.error_count = 0
    db.commit()
    db.close()

    print("\nSESSION INJECTED! Garmin sync restored.")

if __name__ == "__main__":
    main()
