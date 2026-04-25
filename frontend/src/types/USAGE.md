# 类型化 API · 使用指南

`api.generated.ts` 由后端 OpenAPI schema 自动生成（48k 行，444 schemas，662 paths）。
这份文档说明**如何把现有的 `any` 替换成强类型** —— 不要求一次全改，新代码先用，老代码碰到就改。

---

## 一句话用法

```ts
import type { components, paths } from '@/types/api';
```

- `components['schemas']['XxxYyyResponse']` 拿单个 schema
- `paths['/api/v1/...']['get']['responses'][200]['content']['application/json']` 拿某 endpoint 的具体响应

---

## 常用模式

### 1. 拿后端 schema 的现成类型

后端 Pydantic schema 叫什么，前端就这样取：

```ts
// 后端: schemas/health_consultation.py · class HealthConsultationDetail(...)
import type { components } from '@/types/api';
type ConsultationDetail = components['schemas']['HealthConsultationDetail'];

const c: ConsultationDetail = await api.get('/health-consultations/me/4').then(r => r.data);
//   ↑ 强类型：c.title 自动补全, c.fake_field 编译报错
```

替换前：
```ts
const items: any[] = await api.get('...');
items.forEach((c: any) => console.log(c.titlee));  // 拼写错误也不报
```

### 2. 直接锁定某个 endpoint 的响应

```ts
import type { paths } from '@/types/api';
type SleepResponse = paths['/api/v1/garmin-analysis/me/sleep']['get']['responses'][200]['content']['application/json'];
```

适用于：endpoint 没对应单个 schema（返回拼接对象时）。

### 3. POST body 类型

```ts
type ConsultationCreateBody = paths['/api/v1/health-consultations/me']['post']['requestBody']['content']['application/json'];

await api.post('/health-consultations/me', body satisfies ConsultationCreateBody);
```

### 4. axios 强类型 wrapper

```ts
// 替代 any:
const res = await api.get('/health-consultations/me/active');
const data: any = res.data;  // ❌ 弱类型

// 改成:
import type { components } from '@/types/api';
const res = await api.get<components['schemas']['HealthConsultationDetail']>('/health-consultations/me/active');
const data = res.data;  // ✅ 强类型推断
```

---

## 当前 392 处 `any` 的迁移优先级

按文件 any 数量降序：

| 文件 | any 数 | 建议 |
|---|---|---|
| `hooks/useDashboardData.ts` | 23 | 🔴 最优先 — 全 dashboard 数据流的入口 |
| `components/assistant/DataGrid.tsx` | 14 | 🟡 显示组件，类型化能挡 UI 数据 mismatch |
| `app/knowledge/page.tsx` | 13 | 🟡 |
| `components/assistant/TrendsCard.tsx` | 10 | 🟡 |
| `app/supplements/page.tsx` | 10 | 🟡 |
| `services/api/health.ts` | 8 | 🟢 已 deprecated，等改成 generated 直连 |

测试文件 (`__tests__/*`) 的 any 不改 —— 测试本就需要灵活的 mock。

---

## 何时不改

- **真正的 unknown 数据**（用户输入、第三方 webhook 返回）→ 用 `unknown` + 运行时验证（zod / type guard）
- **泛型 prop 占位**（`<T = any>` 给业务方填充）→ 改 `T = unknown`
- **快速原型 / 一次性脚本** → 先不动

---

## ESLint 上报（未来）

当前 `frontend/.eslintrc.json` 没启 `@typescript-eslint/no-explicit-any` 规则
（因为 Next 14 的 ESLint 没安装那个 plugin）。等手工把 392 处压到 < 50，
再装 plugin 把规则改成 `error`，从此挡新增的 `any`。

---

## 重生成 schema（后端 schema 改了之后）

```bash
cd frontend
npm run generate-types
```

跑完会更新 `src/types/api.generated.ts`。任何不匹配的调用立刻显示编译错误。
