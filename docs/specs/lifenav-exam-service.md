# LifeNav 服务端练习与逐次记录

用户已授权实现并交付：服务端可扩充题库、逐次作答入库、Web/手机同步、两小时每日练习。
这是现有 LifeNav 备考功能的升级，不创建健康建议或自动写入人生计划。

## 接口契约（实现约定）

所有接口复用 `/life-navigation` 的本人鉴权、隐私响应和 owner header。
题库是服务器上的版本化审校内容，新增题不要求客户端发布；作答必须服务端判分。
题库不是无限自动生成器；参数变式明确标示，不冒充真题或独立考点。

- `GET /life-navigation/exam/practice?day=YYYY-MM-DD`：只读，返回 `ExamPractice`。
- `POST /life-navigation/exam/attempts`：提交 `ExamAttemptWrite`，返回已落库的 `ExamAttempt`。网络不确定重试必须复用同一 request_id；不同答案使用同一 ID 返回409。
- `GET /life-navigation/exam/attempts?question_id=...&offset=0&limit=50`：只读历史，返回 `{items: ExamAttempt[], total: number}`，按最近在前，包含可证明的旧记录，旧记录显式标明来源。

字段约定：

```typescript
type ExamQuestion = {
 id: string; version: number; subject: '英语'|'数学'|'逻辑'; topic: string;
 prompt: string; options: string[]; source: string; difficulty: string;
};
type ExamProgress = {
 question_id: string; attempt_count: number; latest_correct: boolean;
 ever_wrong: boolean; last_date: string; next_review_date: string | null;
};
type ExamPlanBlock = {subject: string; minutes: number; instruction: string};
type ExamPractice = {
 catalog_version: string; day: string; today: string;
 questions: ExamQuestion[]; progress: ExamProgress[]; queue: string[];
 plan: ExamPlanBlock[]; total_minutes: number; legacy_notice: string;
};
type ExamAttemptWrite = {
 request_id: string; question_id: string; question_version: number;
 choice_index: number; elapsed_seconds: number;
};
type ExamAttempt = {
 id: string; question: ExamQuestion; question_id: string; question_version: number;
 choice_index: number; correct_index: number; correct: boolean;
 explanation: string; study_date: string; answered_at: string | null;
 elapsed_seconds: number | null; source: 'submitted'|'legacy_first'|'legacy_latest';
};
```

提交日期和时间由服务器 Asia/Taipei 确定，客户端不能回填过去或未来。历史日期仅供回看，界面提示切回今天后作答。提交事务保存题目快照/版本、答案、判分和耗时。请求ID按owner唯一，重试不产生重复尝试；相同owner并发提交序列化。记录不能用整个工作区PUT覆盖。

旧80题ID及正文保持不变。读取原工作区中可证明的首次/最近复练作为legacy历史；不迁移删除原数据，不生成未知精确时间，不将缺失中间尝试宣称完整。新流水和旧记录合并后统计，既有旧客户端工作区写入不能擦除新流水。账号删除同步清理流水。

## 每日调度与界面

服务器按实际记录优先安排到期错题与薄弱主题，再补未做题；日期稳定，队列有界，重复明确为复习。正确复练按1/3/7天间隔安排；不把做对一次称为掌握，不用完成勾选推断能力。
计划合计120分钟：英语45、管综40、写作20、复盘15；在计划中显示真实可用题目/耗尽状态，不为了填满预算制造题目。
两端练习区直接使用同一接口，支持上一题/下一题、答题历史、错题本、待复练、全部题库。提交成功后刷新服务端状态；失败保留答案与请求ID，不自动跳下一题，不显示已保存。
进入页面和用户点击刷新时读取最新数据。可见且无正在提交/未提交答案时定时刷新；账号切换丢弃旧响应。不能用localStorage或旧静态题库冒充服务端可用。

## 验收与发布

先红后绿覆盖：跨账号隔离、篡改答案不能控制判分、重试幂等及冲突、并发、时间边界、旧80题保留、错题改正仍留档、逐次历史不覆盖、两端相同队列/进度、上一题只读、失败草稿、刷新不覆盖选择、120分钟和题库耗尽。
数据库使用独立追加表与成对受管迁移，PostgreSQL约束/事务/迁移验证必需。生产无备份策略继续遵守；现有冻结schema gate只允许经独立审查的精确新增表路径，不扩成任意DDL放行。
发布需精确主干CI、独立G4、后端迁移及健康回读、Web发布、兼容当前原生cohort的OTA回执。原生配置已有变化时不得绕过OTA检查。真实手机接收和账号同步另行确认。
