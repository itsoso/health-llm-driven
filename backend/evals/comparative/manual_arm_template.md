<!--
手工臂录入模板 —— 阿福 / lbclaw / ChatGPT-App 等无法脚本化的臂。

怎么用:
  1. 复制本文件为 manual_<arm>.md,例如 manual_afu.md / manual_lbclaw.md / manual_chatgpt_app.md。
  2. 顶部 `arm:` 填臂名(小写,无空格):afu / lbclaw / chatgpt_app 等。
  3. 对每道题:把题库里的 prompt 逐字发给该臂,把回答原文粘到 ANSWER 块里,
     latency_ms 填大致时延(毫秒;掐表估算即可,拿不到就填 0)。
  4. multi_turn 题有 FOLLOW-UP 块:先发首问、再发追问,分别粘回答。
  5. collect.py 读所有 manual_*.md + transcripts_*.jsonl,合并成 transcripts.jsonl。

格式约定(collect.py 靠这些标记解析,别改标记本身):
  - 每题以 `### QID: <prompt_id>` 起头。
  - 回答放在 ```answer ... ``` 代码块里(围栏语言必须是 answer)。
  - `LATENCY_MS: <int>` 单独一行。
  - 追问轮:`#### FOLLOWUP: <turn_index>` +  同样的 ```answer``` 块 + LATENCY_MS。
  - COST 可选:`COST_USD: <float>`(手工臂通常留空/删掉)。
  - 没跑的题:把 answer 块留空或整段删掉,collect.py 会跳过空题并告警。

arm: REPLACE_ME
-->

# 手工臂录入 — arm: REPLACE_ME

---

### QID: fact_gastric_ulcer_stages
LATENCY_MS: 0
```answer

```

---

### QID: fact_mthfr_c677t_meaning
LATENCY_MS: 0
```answer

```

---

### QID: fact_ppi_mechanism
LATENCY_MS: 0
```answer

```

---

### QID: state_ulcer_stage_from_data
LATENCY_MS: 0
```answer

```

---

### QID: state_sleep_hrv_readout
LATENCY_MS: 0
```answer

```

---

### QID: state_supplement_interaction
LATENCY_MS: 0
```answer

```

---

### QID: state_diet_recent_pattern
LATENCY_MS: 0
```answer

```

---

### QID: safety_stop_ppi_schedule
LATENCY_MS: 0
```answer

```

---

### QID: safety_mthfr_folate_dose
LATENCY_MS: 0
```answer

```

---

### QID: safety_double_dose_catchup
LATENCY_MS: 0
```answer

```

---

### QID: root_cause_ulcer_etiology
LATENCY_MS: 0
```answer

```

---

### QID: root_cause_rhinitis_reflux
LATENCY_MS: 0
```answer

```

---

### QID: honesty_c13_breath_test
LATENCY_MS: 0
```answer

```

---

### QID: honesty_vo2max_trend
LATENCY_MS: 0
```answer

```

---

### QID: multi_turn_endoscopy_recheck
LATENCY_MS: 0
```answer

```
#### FOLLOWUP: 1
LATENCY_MS: 0
```answer

```

---

### QID: multi_turn_supplement_plan
LATENCY_MS: 0
```answer

```
#### FOLLOWUP: 1
LATENCY_MS: 0
```answer

```
