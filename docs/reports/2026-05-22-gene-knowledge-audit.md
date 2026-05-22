# Gene Knowledge Audit

- Version: `dd1cad7`
- Compiled at: `2026-05-19T00:24:00.429501+00:00`

## Summary
- `gene_entities`: 14
- `snp_registry`: 22
- `claims`: 18
- `gene_rules`: 10

## Tier Coverage

### Tier 0 用药安全红线
- Coverage: 4/12
- Missing rules: HLA-A*31:01, HLA-B*15:02, HLA-B*58:01, VKORC1, G6PD, DPYD, TPMT, NUDT15
- Missing claims: DPYD, G6PD, HLA-A*31:01, HLA-B*15:02, HLA-B*58:01, NUDT15, TPMT, VKORC1
- Missing authority sources: HLA-A*31:01, HLA-B*15:02, HLA-B*58:01, VKORC1, G6PD, DPYD, TPMT, NUDT15

### Tier 1 基因 + 化验闭环
- Coverage: 7/7

### Tier 2 生活方式倾向
- Coverage: 3/5
- Missing claims: COMT, VDR

### Tier X 待确认筛查
- Coverage: 0/4
- Missing claims: ATP7B, BRCA1, BRCA2, CFTR

## Quality Gates
- Claims missing `applies_when`: 0
- Claims missing boundary: 0
- Drug claims missing clinician boundary: 0

## 下一步
- 补齐 Tier 0 用药安全规则，优先 HLA-B*58:01/HLA-B*15:02/CYP2D6/DPYD/TPMT/NUDT15。
- 为 CFTR/ATP7B 等罕见病位点建立 confirmation_only 边界，防止 DTC 结果显示为疾病高风险。
