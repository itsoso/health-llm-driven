# Reva System Map — Agent Global Context

> DO NOT EDIT — generated from docs/_generated/system-map.json.
> Navigation only: verify behavior in source code and tests.

## Global components

- `component.backend-api` — FastAPI Backend (kind=component; coverage=declaration; owner=backend; domain=health-os; lifecycle=production; trust_boundary=health-backend; data_classes=L1,L2,L3,L4)
- `component.celery-beat` — Celery Beat (kind=component; coverage=declaration; owner=backend; domain=health-os; lifecycle=production)
- `component.celery-worker` — Celery Worker (kind=component; coverage=declaration; owner=backend; domain=health-os; lifecycle=production; trust_boundary=health-backend; data_classes=L2,L3,L4)
- `component.frontend` — Web Frontend (kind=component; coverage=declaration; owner=web; domain=health-os; lifecycle=production; data_classes=L1,L2,L3)
- `component.mac` — Mac App (kind=component; coverage=declaration; owner=mac; domain=health-os; lifecycle=production; data_classes=L1,L2,L3)
- `component.mcp-server` — MCP Server (kind=component; coverage=declaration; owner=backend; domain=health-os; lifecycle=production; data_classes=L1,L2,L3)
- `component.mobile` — Mobile App (kind=component; coverage=declaration; owner=mobile; domain=health-os; lifecycle=production; trust_boundary=user-device; data_classes=L1,L2,L3,L4)
- `component.watch` — Watch App (kind=component; coverage=declaration; owner=watch; domain=health-os; lifecycle=production; trust_boundary=user-device; data_classes=L1,L2,L3)

## Cross-flow relations

- `component.backend-api` --dependsOn--> `resource.apns` (flows=agenda,safety; coverage=declaration)
- `component.backend-api` --dependsOn--> `resource.garmin` (flows=device-sync; coverage=declaration)
- `component.backend-api` --dependsOn--> `resource.llm-provider` (flows=agent-chat; coverage=declaration)
- `component.backend-api` --dependsOn--> `resource.redis` (flows=agent-chat,safety; coverage=declaration)
- `component.backend-api` --providesApi--> `api.health-v1` (flows=agenda,agent-chat,device-sync,health-record,safety; coverage=declaration)
- `component.backend-api` --readsFrom--> `resource.chromadb` (flows=agent-chat; coverage=declaration)
- `component.backend-api` --writesTo--> `resource.postgresql` (flows=agenda,health-record,safety; coverage=declaration)
- `component.celery-beat` --publishesTo--> `resource.celery-queue` (flows=background-jobs; coverage=declaration)
- `component.celery-worker` --consumesFrom--> `resource.celery-queue` (flows=background-jobs; coverage=declaration)
- `component.celery-worker` --writesTo--> `resource.postgresql` (flows=background-jobs; coverage=declaration)
- `component.frontend` --consumesApi--> `api.health-v1` (flows=agenda,health-record,safety; coverage=declaration)
- `component.mac` --consumesApi--> `api.health-v1` (flows=agenda,agent-chat,health-record,safety; coverage=declaration)
- `component.mcp-server` --consumesApi--> `api.health-v1` (flows=mcp; coverage=declaration)
- `component.mcp-server` --providesApi--> `api.mcp` (flows=mcp; coverage=declaration)
- `component.mobile` --consumesApi--> `api.health-v1` (flows=agenda,agent-chat,device-sync,health-record,safety; coverage=declaration)
- `component.mobile` --dependsOn--> `resource.expo-updates` (flows=mobile-ota; coverage=declaration)
- `component.mobile` --dependsOn--> `resource.healthkit` (flows=device-sync; coverage=declaration)
- `component.watch` --consumesApi--> `api.health-v1` (flows=agenda,health-record,safety; coverage=declaration)

## Non-complete coverage

- `api_boundaries`: declaration; limitation=首期登记稳定 API 边界，不枚举所有动态端点。
- `mobile_navigation`: partial; limitation=只包含静态字面量跳转；变量跳转和通知深链不在内。
- `runtime_dependencies`: partial; limitation=外部服务与关键数据资源由显式声明覆盖，运行时条件依赖可能不在内。

## On-demand detail

Run `python3.12 scripts/system_map_context.py` with one selector; use `--counts` only when live architecture counts are required.
