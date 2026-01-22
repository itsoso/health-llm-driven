# Security Hardening And Dependency Governance Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove unsafe defaults, tighten CORS and upload access, and lock dependencies with a repeatable audit process.

**Architecture:** Enforce required secrets at startup and in configuration, derive encryption keys only from validated secrets, configure CORS via explicit allowlists, and harden file uploads/serving. Lock dependency versions in both Python and Node and document audit steps.

**Tech Stack:** FastAPI, Pydantic Settings, SQLAlchemy, Next.js, pnpm/npm, pytest.

---

### Task 1: Enforce required secrets and remove default fallbacks

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/main.py`
- Test: `backend/tests/unit/test_config_security.py`
- Modify: `backend/.env.example`

**Step 1: Write the failing test**

```python
import pytest
from app.config import Settings

def test_settings_rejects_default_secret_key():
    with pytest.raises(ValueError):
        Settings(secret_key="your-super-secret-key-change-in-production")
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/unit/test_config_security.py::test_settings_rejects_default_secret_key -v`  
Expected: FAIL (no validation yet)

**Step 3: Write minimal implementation**

```python
from pydantic import field_validator

@field_validator("secret_key")
@classmethod
def validate_secret_key(cls, v: str):
    if not v or "change-in-production" in v:
        raise ValueError("SECRET_KEY must be set to a strong value")
    return v
```

**Step 4: Add startup check to fail fast**

```python
def startup_event():
    settings.validate_required_security()
```

**Step 5: Update `.env.example` with required keys**

Add `SECRET_KEY=...` and `GARMIN_ENCRYPTION_KEY=...` placeholders plus guidance.

**Step 6: Run test to verify it passes**

Run: `pytest backend/tests/unit/test_config_security.py::test_settings_rejects_default_secret_key -v`  
Expected: PASS

**Step 7: Commit**

```bash
git add backend/app/config.py backend/main.py backend/tests/unit/test_config_security.py backend/.env.example
git commit -m "security(config): enforce required secrets at startup"
```

---

### Task 2: Align auth and device encryption with validated secrets

**Files:**
- Modify: `backend/app/services/auth.py`
- Modify: `backend/app/models/device_credential.py`
- Test: `backend/tests/unit/test_auth_secrets.py`

**Step 1: Write the failing test**

```python
from app.config import settings
from app.services import auth

def test_auth_uses_settings_secret_key():
    assert auth.SECRET_KEY == settings.secret_key
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/unit/test_auth_secrets.py::test_auth_uses_settings_secret_key -v`  
Expected: FAIL (auth reads env directly)

**Step 3: Write minimal implementation**

```python
# auth.py
from app.config import settings
SECRET_KEY = settings.secret_key
```

```python
# device_credential.py
from app.config import settings
SECRET_KEY = settings.secret_key
```

**Step 4: Run test to verify it passes**

Run: `pytest backend/tests/unit/test_auth_secrets.py::test_auth_uses_settings_secret_key -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/services/auth.py backend/app/models/device_credential.py backend/tests/unit/test_auth_secrets.py
git commit -m "security(auth): use validated settings secrets"
```

---

### Task 3: CORS allowlist via env configuration

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/main.py`
- Test: `backend/tests/unit/test_cors_config.py`
- Modify: `backend/.env.example`

**Step 1: Write the failing test**

```python
from app.config import Settings

def test_cors_origins_parse():
    settings = Settings(cors_allow_origins="https://a.com,https://b.com")
    assert settings.cors_allow_origins_list == ["https://a.com", "https://b.com"]
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/unit/test_cors_config.py::test_cors_origins_parse -v`  
Expected: FAIL (no parsing yet)

**Step 3: Write minimal implementation**

```python
cors_allow_origins: str = ""

@property
def cors_allow_origins_list(self):
    return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]
```

**Step 4: Wire CORS to allowlist**

```python
allow_origins=settings.cors_allow_origins_list
```

**Step 5: Run test to verify it passes**

Run: `pytest backend/tests/unit/test_cors_config.py::test_cors_origins_parse -v`  
Expected: PASS

**Step 6: Commit**

```bash
git add backend/app/config.py backend/main.py backend/tests/unit/test_cors_config.py backend/.env.example
git commit -m "security(cors): configure allowlist from env"
```

---

### Task 4: Harden uploads (auth on download + content validation)

**Files:**
- Modify: `backend/app/api/upload.py`
- Test: `backend/tests/integration/test_upload_security.py`

**Step 1: Write the failing test**

```python
def test_download_requires_auth(client):
    res = client.get("/api/v1/upload/files/diet/test.jpg")
    assert res.status_code in (401, 403)
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/integration/test_upload_security.py::test_download_requires_auth -v`  
Expected: FAIL (download is public)

**Step 3: Write minimal implementation**

```python
@router.get("/files/{category}/{filename}")
async def get_uploaded_file(..., current_user: User = Depends(get_current_user_required)):
    ...
```

**Step 4: Add content validation on upload**

```python
import imghdr
detected = imghdr.what(None, h=content)
if detected not in {"jpeg", "png", "gif", "webp"}:
    raise HTTPException(status_code=400, detail="文件内容不是有效图片")
```

**Step 5: Run test to verify it passes**

Run: `pytest backend/tests/integration/test_upload_security.py::test_download_requires_auth -v`  
Expected: PASS

**Step 6: Commit**

```bash
git add backend/app/api/upload.py backend/tests/integration/test_upload_security.py
git commit -m "security(upload): require auth and validate content"
```

---

### Task 5: Lock dependency versions (Python + Node)

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `backend/requirements-fixed.txt`
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json` or `pnpm-lock.yaml` (depending on package manager)

**Step 1: Pin Python dependencies**

Replace all `>=` with exact versions that match current working versions.

**Step 2: Pin Node dependencies**

Replace all `^` with exact versions.

**Step 3: Regenerate lockfiles**

Run: `pnpm install` or `npm install` (use the project’s standard)  
Expected: lockfile updated with exact versions

**Step 4: Commit**

```bash
git add backend/requirements.txt backend/requirements-fixed.txt frontend/package.json pnpm-lock.yaml frontend/package-lock.json
git commit -m "security(deps): pin dependency versions"
```

---

### Task 6: Add dependency audit workflow and documentation

**Files:**
- Create: `docs/SECURITY.md`
- Modify: `backend/requirements.txt` (add audit note comment)
- Modify: `frontend/package.json` (add audit script if needed)

**Step 1: Document audit commands**

```markdown
pip-audit -r backend/requirements.txt
npm audit --prefix frontend
```

**Step 2: Add package scripts (optional)**

```json
"audit": "npm audit"
```

**Step 3: Commit**

```bash
git add docs/SECURITY.md frontend/package.json
git commit -m "docs(security): add dependency audit procedure"
```

---

### Task 7: Full verification

**Step 1: Run backend tests**

Run: `pytest backend/tests/unit/test_config_security.py backend/tests/unit/test_auth_secrets.py backend/tests/unit/test_cors_config.py backend/tests/integration/test_upload_security.py -v`  
Expected: PASS

**Step 2: Run audits**

Run: `pip-audit -r backend/requirements.txt`  
Run: `npm audit --prefix frontend`  
Expected: No high/critical vulnerabilities (document any exceptions)

**Step 3: Commit audit notes if needed**

```bash
git add docs/SECURITY.md
git commit -m "security(audit): record audit results"
```

---

Plan complete and saved to `docs/plans/2026-01-21-security-hardening.md`. Two execution options:

1. Subagent-Driven (this session) — I dispatch a fresh subagent per task, review between tasks, fast iteration  
2. Parallel Session (separate) — Open a new session with executing-plans, batch execution with checkpoints

Which approach?*** End Patch}Wait patch ended? I included end patch maybe wrong. Need correct apply_patch. Let's redo properly. Ensure tool input proper with *** Begin Patch etc. I'll redo. Comment in analysis: use apply_patch. Let’s run. We'll apply patch with correct format. Ensure no extra text. Use comment channel with tool call. Let's fix.}
