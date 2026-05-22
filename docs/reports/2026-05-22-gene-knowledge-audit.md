# Gene Knowledge Audit

- Version: `dd1cad7`
- Compiled at: `2026-05-22T15:20:05.568518+00:00`

## Summary
- `gene_entities`: 24
- `snp_registry`: 26
- `claims`: 28
- `gene_rules`: 18

## Tier Coverage

### Tier 0 用药安全红线
- Coverage: 12/12

### Tier 1 基因 + 化验闭环
- Coverage: 7/7

### Tier 2 生活方式倾向
- Coverage: 3/5
- Missing claims: COMT, VDR

### Tier X 待确认筛查
- Coverage: 2/4
- Missing claims: BRCA1, BRCA2

## Quality Gates
- Claims missing `applies_when`: 0
- Claims missing boundary: 0
- Drug claims missing clinician boundary: 0

## 下一步
- 为 BRCA1/BRCA2 建立 confirmation_only 边界，防止 DTC 结果显示为疾病高风险。
