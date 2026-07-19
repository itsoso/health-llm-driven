# Chinese-CLIP 本地饮食识别优化设计

> 日期：2026-07-19  
> 范围：`codex/local-first-private-g2` 独立 G2 评测支线；不接生产饮食页  
> 前置设计：`docs/plans/2026-07-18-chinese-clip-local-food-vision-design.md`

## 1. 目标与顺序

按用户确认的顺序完成三项优化：

1. 提升图像预处理质量并减少 Core ML 输入拷贝开销；
2. 让既有 `non_food` 拒识分支获得真实的本地负标签；
3. 删除可手工填写的 FP16/压缩身份精度差，改为由两份冻结测试报告确定性派生。

这些优化只增强独立模型 spike。授权质量集、代表性真机和物理隐私证据仍缺失，因此本轮不得把 Chinese-CLIP 的 G2 状态改成 PASS，也不得接入生产写路径。

## 2. Correct Course：预处理必须匹配官方实现

最初审计建议把整图改为“等比缩放 + 中心裁切”。复核固定代码 revision 后发现该假设不成立：Chinese-CLIP 官方 `image_transform` 明确执行 `Resize((224, 224), BICUBIC)`，随后 RGB 转换、张量化和固定 mean/std 归一化。

因此采用以下设计：

- 保留整图和显著区域直接缩放到 224×224 的语义，不加入中心裁切；
- 把当前最近邻采样替换为确定性的 bicubic 采样；
- EXIF 方向仍在采样坐标层纠正；
- 边缘像素夹取、插值结果限制到 8-bit RGB 范围，再使用官方 mean/std；
- 用固定合成像素图和已固定 Python 环境中的官方预处理结果做 golden parity 测试；
- `MLMultiArray` 仍由调用内新建，但 Float32 张量使用连续内存一次写入，删除逐元素 `NSNumber` 装箱。

若 golden parity 超出一个 8-bit 量化步对应的归一化误差，测试失败；不通过降低容差掩盖算法差异。

## 3. 标签库 v2 与非食物拒识

当前排序器已有 `LocalFoodLabelKind.nonFood`，但 v1 标签库全是食物，运行时负标签分支没有输入。v2 标签库采用同一固定文本塔和二进制格式，新增 owner-authored 非食物身份族，并为食物/非食物使用不同的固定中文 prompt 模板。

约束：

- 食物 ID 必须以 `food.` 开头；负标签 ID 必须以 `non_food.` 开头且类别为 `non_food`；
- 负标签只描述视觉身份，如人物、宠物、风景、文档、屏幕、日常物品和空餐具；
- 标签源继续递归拒绝营养、热量、克数、份量等字段；
- Swift loader 继续只由 `category == non_food` 映射负标签，负标签不会出现在候选食物列表；
- 排序器只有在负标签达到冻结分数地板且不低于最高食物分数时才返回 `.nonFood`，否则仍返回 `.unknown` 或食物候选；
- v2 生成物必须二次生成字节一致，并更新来源摘要、输出摘要和实际安装字节数。

负标签能使拒识路径可运行，但不能代替授权 `non_food_adversarial` 数据集的 0.98 拒识率验证。该质量 Gate 继续 BLOCK。

## 4. 原始真机报告与派生变体证据分离

当前压缩宿主接受 `--fp16-delta` 数值，报告会无条件回写该值。即使文档要求它来自冻结测试集，工具本身仍允许手工伪造。新设计删除该输入和逐次报告字段：

```text
授权数据清单（>=300，冻结 calibration/test）
        │
        ├── FP16 真机原始 test report ──┐
        │                               ├── scorer compare ──> variant evidence
        └── int8 真机原始 test report ─┘
```

- 宿主生成器是原始证据采集器，不接受 delta，也不产生 PASS；
- 素材清单必须至少 300 case、无私人数据、ID 唯一、包含全部冻结分层和 calibration/test split；
- 宿主只执行 `test` split，校准数据不进入最终质量报告；
- FP16 与 int8 原始报告都不声明二者差值；
- `score ... compare` 同时读取冻结数据清单、两份完整 test report 和版本化 Core ML 变体 manifest，验证模型 revision、标签版本、数据版本、case 集完全一致；
- 身份精度差、质量 Gate、资产字节数和选中变体只能由比较命令计算；输出记录输入文件 SHA-256 和冻结 test case ID 摘要；
- 新 JSON Schema 约束派生证据结构；原始报告 Schema 明确拒绝旧的手填 delta 字段。

没有两份完整报告时，工具只能保持 BLOCK，不能用 embedding cosine、单个 case 或命令行数字替代。

## 5. 安全、隐私与失败边界

- 不读取相册、HealthKit、本地饮食仓库或生产用户数据；素材只能从显式本地目录打包。
- 不添加 URL/网络接口，不上传照片、crop、embedding 或候选。
- 非食物标签和派生报告都不含营养或医疗建议。
- 模型、标签二进制、授权图片和原始报告继续留在 Git 忽略目录；仓库只提交源标签、manifest、Schema、脚本和测试。
- 任一摘要、split、版本、case 集、授权字段或质量阈值不一致都 fail-loud。

## 6. 验收

- Swift golden 测试证明预处理与固定官方 bicubic 输出一致；既有方向、裁切、排序和引擎测试全绿。
- v2 标签库包含可加载的非食物向量；来源与二进制二次生成一致；包体仍低于 50 MiB。
- 宿主 CLI 中不存在 `--fp16-delta`；不足 300 case、缺分层、私人素材和非完整 split 全部被拒绝。
- 比较器只从完整 FP16/int8 test reports 派生 delta，并拒绝模型、标签、数据或 case 不一致。
- JSON Schema、Python、Ruby、Swift、generic iOS build、doc drift 和 dossier consistency 全绿。
- 最终 dossier 仍诚实记录 Chinese-CLIP G2 为 BLOCK，直到外部授权数据和真机矩阵齐备。
