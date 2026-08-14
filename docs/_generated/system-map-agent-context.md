# Reva System Map — Agent Global Context

> DO NOT EDIT — generated from docs/_generated/system-map.json.
> Navigation input only: verify behavior in source code and tests before deciding or editing.

## Evidence order

1. Executable code, tests, runtime contracts, and registries
2. Code-derived System Map facts
3. Reviewed declarations with explicit coverage
4. Freshness-dated narrative documents

## Global entities

- `api.health-v1` — Health API v1 (kind=api; coverage=declaration)
  source: `backend/app/api/main.py [declaration]`
- `api.mcp` — Reva MCP Tools (kind=api; coverage=declaration)
  source: `mcp-server/server.py [declaration]`
- `component.backend-api` — FastAPI Backend (kind=component; coverage=declaration; owner=backend; domain=health-os; lifecycle=production; trust_boundary=health-backend; data_classes=L1,L2,L3,L4)
  source: `backend/app/api/main.py [declaration]`
- `component.celery-beat` — Celery Beat (kind=component; coverage=declaration; owner=backend; domain=health-os; lifecycle=production)
  source: `backend/app/celery_app.py [declaration]`
- `component.celery-worker` — Celery Worker (kind=component; coverage=declaration; owner=backend; domain=health-os; lifecycle=production; trust_boundary=health-backend; data_classes=L2,L3,L4)
  source: `backend/app/celery_app.py [declaration]`
- `component.frontend` — Web Frontend (kind=component; coverage=declaration; owner=web; domain=health-os; lifecycle=production; data_classes=L1,L2,L3)
  source: `frontend/src/app/ [declaration]`
- `component.mac` — Mac App (kind=component; coverage=declaration; owner=mac; domain=health-os; lifecycle=production; data_classes=L1,L2,L3)
  source: `apps/mac/ [declaration]`
- `component.mcp-server` — MCP Server (kind=component; coverage=declaration; owner=backend; domain=health-os; lifecycle=production; data_classes=L1,L2,L3)
  source: `mcp-server/server.py [declaration]`
- `component.mobile` — Mobile App (kind=component; coverage=declaration; owner=mobile; domain=health-os; lifecycle=production; trust_boundary=user-device; data_classes=L1,L2,L3,L4)
  source: `mobile/app/ [declaration]`
- `component.watch` — Watch App (kind=component; coverage=declaration; owner=watch; domain=health-os; lifecycle=production; trust_boundary=user-device; data_classes=L1,L2,L3)
  source: `apps/watch/ [declaration]`
- `resource.apns` — Apple Push Notification Service (kind=resource; coverage=declaration)
  source: `backend/app/services/notification/ [declaration]`
- `resource.celery-queue` — Celery Queue (kind=resource; coverage=declaration)
  source: `backend/app/celery_app.py [declaration]`
- `resource.chromadb` — ChromaDB (kind=resource; coverage=declaration; data_classes=L2,L3)
  source: `backend/app/services/ [declaration]`
- `resource.expo-updates` — Expo Updates (All Channel Writers and Network Observation Frozen; Local Evidence Only) (kind=resource; coverage=declaration)
  source: `mobile/app.json [declaration]`
- `resource.garmin` — Garmin (kind=resource; coverage=declaration; data_classes=L3)
  source: `backend/app/api/data_collection.py [declaration]`
- `resource.healthkit` — Apple HealthKit (kind=resource; coverage=declaration; data_classes=L3)
  source: `mobile/services/appleHealth.ts [declaration]`
- `resource.ios-simulator-feedback` — Mobile Local Feedback (iOS Exact-UDID Simulator Only; Physical iOS and Android Native Repo CLI Frozen) (kind=resource; coverage=declaration; data_classes=L1)
  source: `scripts/sim-build.sh [declaration]`
- `resource.llm-provider` — LLM Provider Pool (kind=resource; coverage=declaration; data_classes=L2,L3)
  source: `backend/app/services/llm/ [declaration]`
- `resource.mac-release-assets` — Mac Developer ID Protocol Assets (release-dmg Shell Entirely Frozen; Writer-Free Checker Required; Fixed-Root Test Fixture/Local Candidate Only) (kind=resource; coverage=declaration; data_classes=L1)
  source: `apps/mac/scripts/release-dmg.sh [declaration]`
- `resource.postgresql` — PostgreSQL (kind=resource; coverage=declaration; trust_boundary=health-backend; data_classes=L1,L2,L3,L4)
  source: `backend/app/database.py [declaration]`
- `resource.redis` — Redis (kind=resource; coverage=declaration; trust_boundary=health-backend; data_classes=L2,L3)
  source: `backend/app/utils/redis_cache.py [declaration]`
- `resource.release-coordinator` — Release Control (All Network/Writer Modes Frozen; Shell Legacy Literal-False Tombstoned; RC78 Is Not Hostile Bootstrap Trust; Offline Evidence Only) (kind=resource; coverage=declaration; data_classes=L2)
  source: `deploy.sh [declaration]`
- `resource.rokid-native-feedback` — Rokid Native Build/Install (Tracked Gradle, Debug-Sign Build and ADB Frozen; No Reviewed Unsigned Compile/Test Wrapper) (kind=resource; coverage=declaration; data_classes=L1)
  source: `apps/rokid-pushup-glasses/README.md [declaration]`

## Key flows

### agenda
- `component.backend-api` --dependsOn--> `resource.apns` (coverage=declaration; source=`backend/app/services/notification/ [declaration]`)
- `component.backend-api` --providesApi--> `api.health-v1` (coverage=declaration; source=`backend/app/api/main.py [declaration]`)
- `component.backend-api` --writesTo--> `resource.postgresql` (coverage=declaration; source=`backend/app/database.py [declaration]`)
- `component.frontend` --consumesApi--> `api.health-v1` (coverage=declaration; source=`frontend/src/services/ [declaration]`)
- `component.mac` --consumesApi--> `api.health-v1` (coverage=declaration; source=`apps/mac/ [declaration]`)
- `component.mobile` --consumesApi--> `api.health-v1` (coverage=declaration; source=`mobile/services/ [declaration]`)
- `component.watch` --consumesApi--> `api.health-v1` (coverage=declaration; source=`apps/watch/ [declaration]`)

### agent-chat
- `component.backend-api` --dependsOn--> `resource.llm-provider` (coverage=declaration; source=`backend/app/services/llm/ [declaration]`)
- `component.backend-api` --dependsOn--> `resource.redis` (coverage=declaration; source=`backend/app/utils/redis_cache.py [declaration]`)
- `component.backend-api` --providesApi--> `api.health-v1` (coverage=declaration; source=`backend/app/api/main.py [declaration]`)
- `component.backend-api` --readsFrom--> `resource.chromadb` (coverage=declaration; source=`backend/app/services/ [declaration]`)
- `component.mac` --consumesApi--> `api.health-v1` (coverage=declaration; source=`apps/mac/ [declaration]`)
- `component.mobile` --consumesApi--> `api.health-v1` (coverage=declaration; source=`mobile/services/ [declaration]`)

### background-jobs
- `component.celery-beat` --publishesTo--> `resource.celery-queue` (coverage=declaration; source=`backend/app/celery_app.py [declaration]`)
- `component.celery-worker` --consumesFrom--> `resource.celery-queue` (coverage=declaration; source=`backend/app/celery_app.py [declaration]`)
- `component.celery-worker` --writesTo--> `resource.postgresql` (coverage=declaration; source=`backend/app/database.py [declaration]`)

### device-sync
- `component.backend-api` --dependsOn--> `resource.garmin` (coverage=declaration; source=`backend/app/api/data_collection.py [declaration]`)
- `component.backend-api` --providesApi--> `api.health-v1` (coverage=declaration; source=`backend/app/api/main.py [declaration]`)
- `component.mobile` --consumesApi--> `api.health-v1` (coverage=declaration; source=`mobile/services/ [declaration]`)
- `component.mobile` --dependsOn--> `resource.healthkit` (coverage=declaration; source=`mobile/services/appleHealth.ts [declaration]`)

### health-record
- `component.backend-api` --providesApi--> `api.health-v1` (coverage=declaration; source=`backend/app/api/main.py [declaration]`)
- `component.backend-api` --writesTo--> `resource.postgresql` (coverage=declaration; source=`backend/app/database.py [declaration]`)
- `component.frontend` --consumesApi--> `api.health-v1` (coverage=declaration; source=`frontend/src/services/ [declaration]`)
- `component.mac` --consumesApi--> `api.health-v1` (coverage=declaration; source=`apps/mac/ [declaration]`)
- `component.mobile` --consumesApi--> `api.health-v1` (coverage=declaration; source=`mobile/services/ [declaration]`)
- `component.watch` --consumesApi--> `api.health-v1` (coverage=declaration; source=`apps/watch/ [declaration]`)

### mac-release
- `component.mac` --dependsOn--> `resource.mac-release-assets` (coverage=declaration; source=`apps/mac/scripts/release-dmg.sh [declaration]`)

### mcp
- `component.mcp-server` --consumesApi--> `api.health-v1` (coverage=declaration; source=`mcp-server/server.py [declaration]`)
- `component.mcp-server` --providesApi--> `api.mcp` (coverage=declaration; source=`mcp-server/server.py [declaration]`)

### mobile-ota
- `component.mobile` --dependsOn--> `resource.expo-updates` (coverage=declaration; source=`mobile/app.json [declaration]`)

### mobile-simulator
- `component.mobile` --dependsOn--> `resource.ios-simulator-feedback` (coverage=declaration; source=`scripts/sim-build.sh [declaration]`)

### release-planning
- `component.backend-api` --dependsOn--> `resource.release-coordinator` (coverage=declaration; source=`deploy.sh [declaration]`)
- `component.frontend` --dependsOn--> `resource.release-coordinator` (coverage=declaration; source=`deploy.sh [declaration]`)
- `component.mac` --dependsOn--> `resource.release-coordinator` (coverage=declaration; source=`apps/mac/scripts/release-dmg.sh [declaration]`)
- `component.mobile` --dependsOn--> `resource.release-coordinator` (coverage=declaration; source=`scripts/release.py [declaration]`)

### rokid-glasses
- `component.mobile` --dependsOn--> `resource.rokid-native-feedback` (coverage=declaration; source=`apps/rokid-pushup-glasses/README.md [declaration]`)

### safety
- `component.backend-api` --dependsOn--> `resource.apns` (coverage=declaration; source=`backend/app/services/notification/ [declaration]`)
- `component.backend-api` --dependsOn--> `resource.redis` (coverage=declaration; source=`backend/app/utils/redis_cache.py [declaration]`)
- `component.backend-api` --providesApi--> `api.health-v1` (coverage=declaration; source=`backend/app/api/main.py [declaration]`)
- `component.backend-api` --writesTo--> `resource.postgresql` (coverage=declaration; source=`backend/app/database.py [declaration]`)
- `component.frontend` --consumesApi--> `api.health-v1` (coverage=declaration; source=`frontend/src/services/ [declaration]`)
- `component.mac` --consumesApi--> `api.health-v1` (coverage=declaration; source=`apps/mac/ [declaration]`)
- `component.mobile` --consumesApi--> `api.health-v1` (coverage=declaration; source=`mobile/services/ [declaration]`)
- `component.watch` --consumesApi--> `api.health-v1` (coverage=declaration; source=`apps/watch/ [declaration]`)

## Coverage limits

- `api_boundaries`: declaration; source=`backend/app/api/main.py`; limitation=首期登记稳定 API 边界，不枚举所有动态端点。
- `celery_jobs`: complete; source=`backend/app/tasks/`
- `mobile_navigation`: partial; source=`docs/_generated/mobile-nav-graph.json`; limitation=只包含静态字面量跳转；变量跳转和通知深链不在内。
- `mobile_surfaces`: complete; source=`mobile/app/`
- `runtime_dependencies`: partial; source=`docs/system-map/declarations.json`; limitation=外部服务与关键数据资源由显式声明覆盖，运行时条件依赖可能不在内。
- `web_surfaces`: complete; source=`frontend/src/app/`

## Code-derived counts

- api_routers: 166
- celery_tasks: 72
- mobile_routes: 127
- model_files: 116
- safety_rules_total: 65
- service_files: 410
- specialists: 13
- twin_partitions: 15
- web_pages: 73
