# WorkBuddy 自动化模板

本目录交付的是“可复制的定时任务定义”，不是某个 WorkBuddy 账号的登录态或任务数据库。

## 接手方只需做一次的动作

在 WorkBuddy 中打开本仓库工作区，然后让它读取：

```text
.workbuddy/automations/policy-ai-sync.template.json
```

并创建一个名为“UE-Agent 全城市政策同步”的每日 08:00（Asia/Shanghai）定时任务，任务内容使用 JSON 中的 `prompt`，调用项目级 Skill `policy-ai-crawler`。

这样以后新增城市不需要新增 WorkBuddy 任务。定时任务每次从 UE-Agent API 读取城市清单，发现没有来源的城市时先执行 `policy-city-onboarding`，再执行政策检索与回传。

## 为什么不能直接复制定时任务记录

WorkBuddy 的定时任务实体属于创建人的账号，包含账号 ID、工作区状态和本地权限，不适合写进 Git。仓库只保存不含账号信息的任务模板；Skill、执行步骤、调用接口和数据安全规则均随项目交付。

WorkBuddy 必须在运行 UE-Agent API 的同一台机器上，或能够访问配置的 `apiBaseUrl`。本地模式默认是 `http://127.0.0.1:8000`。
