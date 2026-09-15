---
name: policy-city-onboarding
description: "新增城市的一键来源配置：按城市名（C1）检索定位权威数据源（市医保局/市统计局/市政府 + 省级复用），批量入库并逐个验证可达性，然后接上抓取与字段抽取。收到「新增城市」「给某市配来源」「初始化城市政策资料」「一键配置数据源」等请求时触发。"
metadata: {"workbuddy":{"emoji":"🏙️","agent_created":true,"requires":{"commands":["curl","python3"]}}}
---

# 新增城市 · 一键配置政策数据源

## 这个 skill 解决什么

给一个新城市配好「政策资料来源」，再让它能把 20 个自动爬虫字段填上。

不做这件事的话，每新增一个城市都要人工翻网站、找医保局/统计局/政府门户的地址、逐个粘贴——
本 skill 把这套流程固定下来：**AI 负责检索与判断，API 负责入库与验证**。

> 分工：**本 skill 主线是「把来源配好并验证」**（另附配完之后的两件事：
> 对比图与公网发布）；
> 「抽字段」的详细规则见 skill **`policy-ai-crawler`**（编码、国密证书、quote 闸门等都在那边）。

---

## 前置条件

| 项 | 说明 |
| --- | --- |
| 项目根 | 本仓库根目录（`apps/web` + `services/api` 的 monorepo） |
| `BASE_URL` | 默认 `http://127.0.0.1:8000` |
| 本地 API 未启动时 | 用 venv 的 python 起（**不要用 uv**，避免依赖解析）：`PYTHONPATH=services/api services/api/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --log-level warning`，然后轮询 `/api/health` 直到 200（约 2 秒） |
| `TOKEN` | 环境变量 `UE_AGENT_AGENT_TOKEN`；未配置时本地放行 |

> **本机 curl 必加 `--noproxy '*'`**，否则会被系统代理劫持成 `HTTP=000`。

---

## 流程（四步）

### Step 1 · 先问：这个省已经有城市配过了吗？

**省级来源在一个省内是共享的** —— 省医保局、省统计局、省政府、省级长护险文件……
这些对同省所有城市都适用。所以先看库里有没有同省城市：

```bash
curl -s --noproxy '*' "$BASE_URL/api/policies/sources" | python3 -c "
import json,sys
for s in json.load(sys.stdin): print(s['cityId'], '|', s['name'][:40], '|', s['status'])
"
```

若同省已有城市 → **省级来源直接抄过来复用**，本步即可省掉大半工作量。
若没有 → 连省级一起检索（见 Step 2 的「省级」一栏）。

### Step 2 · 检索定位入口（这一步只能靠 AI）

要找到的东西按优先级：

| 类别 | 目标 | 典型 |
| --- | --- | --- |
| **省级**（若无同省城市） | 省医保局 / 省统计局 / 省政府 / 省级长护险政策原文 | `ybj.<省>.gov.cn`、`tjj.<省>.gov.cn`、`www.<省>.gov.cn` |
| **市级·政策** | 市医保局（长护险政策、待遇标准、定点机构） | 见下方「域名规律」 |
| **市级·人口** | 市统计局（常住人口、老龄化率、参保人数） | `tjj.<市>.gov.cn` |
| **市级·综合** | 市政府门户（区划、面积、综合数据） | `www.<市>.gov.cn` |
| **市级·栏目页** | 统计公报索引 / 统计年鉴索引 / 医保局数据发布栏目 | 顺着栏目入口点进去 |

#### 域名规律只对一半，别只靠猜

实测（岳阳）：

| 猜法 | 结果 |
| --- | --- |
| `www.{市}.gov.cn` | ✓ |
| `tjj.{市}.gov.cn` | ✓ |
| `ybj.{市}.gov.cn` | ✗ 不通 |
| `ylbzj.{市}.gov.cn` | ✗ 不通 |

**真实情况**：不少城市的医保局**不是独立域名，而是挂在市政府门户的子目录下**
（岳阳是 `www.yueyang.gov.cn/yyyb/`）。**必须联网检索确认**，猜出来的域名一律要验证。

#### 检索要点

1. 带上当前年份与「长期护理保险」「统计公报」这类关键词，才能搜到**最新一期**；
2. 优先 `*.gov.cn`，**不要**聚合站/论坛/自媒体；
3. **优先「栏目页」而不是部门首页** —— 栏目页每年新增条目、内容会变，
   是发现新一期的入口；首页带滚动新闻，每轮都会变但抽不出值；
4. **顺手捡「建议提案答复」**：这类页面常含人口/参保/基金等具体数字，是城市数据的金矿
   （岳阳的 C3/C4/C10/C11 全部来自答复页，而不是统计公报）。

### Step 3 · 批量入库 + 自动验证（一个请求搞定）

```bash
curl -s --noproxy '*' -X POST "$BASE_URL/api/policies/cities/<城市ID>/sources/bulk" \
  -H 'content-type: application/json' -H "x-ue-agent-token: $TOKEN" -d '{
  "sources": [
    {"name":"<市>医疗保障局","url":"http://...","note":"市级长护险政策（P 档）"},
    {"name":"<市>统计局","url":"http://...","note":"城市人口（C3/C4/C5/C10/C11）"},
    {"name":"<市>人民政府","url":"http://...","note":"区划/面积/综合数据"},
    {"name":"<省>医疗保障局","url":"http://...","note":"省级政策（复用）"}
  ],
  "verify": true
}'
```

**城市 ID 用城市名**（中文），跟政策页地址一致 —— 例如 `/policies/岳阳` 就传 `岳阳`。
拿不准先打 `/api/policies/overview` 看它报的 `cityId`。

返回逐条结果，**读懂 `status` 决定下一步**：

| `status` | 含义 | 处理 |
| --- | --- | --- |
| `verified` | 建好了、抓通了（含 `httpStatus` / `title`） | 留用 |
| `duplicate` | 该城市已有同 URL | 忽略 |
| `rejected` | 非 http/https | 换链接 |
| `unreachable` | 抓不通，**已自动停用** | 看 `message`：多为国密证书（换 `http://`）或域名猜错 |

> `unreachable` 的不会留成活跃来源 —— 停用后 `crawl-all` 会跳过它，不会反复失败。
> 人工改好 URL 后在页面上「启用」即可。

**保守策略**：一次别提交太多（建议 ≤ 12 条），先把「城市级 3 条 + 省级复用」跑通，
再按 `policy-ai-crawler` 的字段族补栏目页与具体文档。

### Step 4 · 抓取 + 抽字段

```bash
curl -s --noproxy '*' -X POST "$BASE_URL/api/policies/cities/<城市ID>/crawl-all"
```

看返回的 `changed`：**只有「有更新」的来源才值得送 AI 抽取**（`unchanged` 说明内容没变）。
抽取规则（quote 必填、C6/C7/C8 禁止估算、P2 存 0–1、枚举归一化……）全部见
skill **`policy-ai-crawler`**，不要在这里重复实现。

---

## 配完来源之后：发起一轮实时政策研究

新增城市完成来源配置后，建议立即创建一轮 research run，让 WorkBuddy 按当前年份再次检索最新政策和统计资料，而不是只依赖固定 URL：

```bash
RUN=$(curl -s --noproxy '*' -X POST "$BASE_URL/api/policies/research-runs" \
  -H 'content-type: application/json' -H "x-ue-agent-token: $TOKEN" \
  -d '{"cityId":"<城市ID>","trigger":"workbuddy","scope":"all"}')
```

读取返回的 `taskPrompt` 或 `GET /api/policies/research-runs/{runId}/brief`，按 `policy-ai-crawler` skill 完成候选来源、原文抓取和字段回传。未配置 token 的本地 Demo 可以省略鉴权头。这样新增城市的第一次“找最新资料”与后续“更新政策”使用同一套协议。

在全城市定时任务中，如果 `/api/projects` 发现新城市没有启用来源，先执行本 Skill 完成来源
发现与验证，再交给 `policy-ai-crawler` 执行 research run。不要为每个城市复制一份
WorkBuddy 定时任务；统一任务模板在 `.workbuddy/automations/policy-ai-sync.template.json`。

## 配完来源之后：仪表盘对比图是自动的，不用改代码

新城市跑完测算后，**「城市对比」视图会自动带上它**——趋势图按城市分线、
图例自动标城市名、柱状图与城市比较表同样自动。前端画线是按返回的城市列表循环的，
没有写死任何城市。

两个前提与一个上限，向用户交代清楚：

| 项 | 说明 |
| --- | --- |
| **必须有测算结果** | 只配了政策来源、还没跑城市测算的城市**不会**出现在对比图上（`hasValidResult` 且未过期才参与） |
| **上限 5 个城市** | PRD 9.2 的 `MAX_COMPARE_CITIES = 5`，勾选超过 5 个自动退回总览视图 |
| **配色 5 种** | `--chart-1` 到 `--chart-5` 恰好与上限一一对应；未来要突破 5 城才需要扩配色（并建议每城加不同虚线线型） |

所以新增城市的完整闭环是：**配来源 → 抓字段 → 人工「采用」建议值 → 跑城市测算 → 对比图自动出现**。

---

## 把项目发布成公网链接（WorkBuddy，零配置）

拿到本项目后**不需要自己配服务器**：发布脚本已经写好（`scripts/publish-install.sh`
+ `scripts/publish-start.sh`），在 WorkBuddy 对话里说一句「**发布这个项目**」即可。
AI 会调用发布能力，参数全部用默认推荐值：

| 参数 | 值 | 说明 |
| --- | --- | --- |
| 目录 | 仓库根 | monorepo 根目录 |
| 端口 | 3000 | 唯一公网入口 |
| 安装命令 | `bash scripts/publish-install.sh` | 建 `.venv-publish` 装 API 依赖 + pnpm 装前端依赖 |
| 启动命令 | `bash scripts/publish-start.sh` | 单端口模式：Next.js 监听 `$PORT`，`/api/*` rewrite 代理到本机 FastAPI |

发布成功后会得到一个 `https://*.app.workbuddy.link` 的公网地址，
浏览器直接打开就能用（前端把 `NEXT_PUBLIC_API_BASE_URL` 置空走同源相对路径，
**没有跨域问题**）。

### 发布时的三个坑（提前知道，少走弯路）

1. **工具可能报失败，但实际已发布成功。** 判据不是工具的返回文案：
   - 看日志 `~/.workbuddy/logs/daemon.log` 里的 `SitesDeploy`，出现 `artifactRelease.ok` 即产物已生成；
   - 最终以**自己复核**为准：请求一个旧版没有的接口（如 `GET /api/policies/crawl-targets`，
     返回 200 且 `fieldCatalog` 有 20 项 = 新代码已上线）。
2. **全新发布不会自动导入业务数据**，库是空的 —— `bootstrap.py` 只在项目内存在
   `projects.json` 时才导入。想要「空库起步」就什么都不做；沙箱复用时
   `runtime-data/` 会跨发布保留上一次的数据，介意就删掉该目录再发布。
3. **同一份代码反复发布**：不给 appId 时每次都会新建 app，但分享链接是同一个哈希地址，
   效果等同「覆盖原链接」，不用重新发链接给别人。

---

## 相关文件

| 路径 | 内容 |
| --- | --- |
| `../policy-ai-crawler/SKILL.md` | **抽取阶段的手册**（quote 闸门、单位换算、编码/国密等踩坑） |
| `services/api/app/api/routes.py` | `/policies/...` 全部接口（本 skill 用的 bulk / crawl-all / freshness 都在这） |
| `services/api/app/domain/policy/agent_service.py` | 派活清单与 7 项回传校验的确定性逻辑 |
| `scripts/publish-install.sh` / `scripts/publish-start.sh` | **WorkBuddy 发布的安装/启动脚本**（单端口模式，见上节） |
| `docs/superpowers/specs/2026-09-10-policy-ai-crawl-design.md` | 为什么「抓取留在 API、AI 只负责理解」 |


## 完成后自检

- [ ] `GET /api/policies/crawl-targets` 的 `cities[]` 里**出现了这个城市**（没来源的城市不会出现）
- [ ] 该城市来源全部 `active`，没有 `unreachable` 遗留
- [ ] `POST .../crawl-all` 返回 `failed = 0`
- [ ] `GET /api/policies/cities/<城市ID>/source-freshness` 无 `stale`
- [ ] 抽到的建议值**带来源归属**（回传时传 `sourceId`，否则表格里来源列是空的）
- [ ] 明确告诉用户：**建议值需人工在城市公式页逐条「采用」才生效**
- [ ] 明确告诉用户：**要让新城市出现在「城市对比」图上，还需跑完城市测算**
      （只配来源不测算不会出现；对比上限 5 城，见上节）

## 红线

1. **不猜域名就入库。** 猜的 URL 一律先过 `sources/bulk` 的验证；
2. **不把聚合站/自媒体当来源**（只收政府、统计、官方机构）；
3. **不自己下载网页** —— 抓取一律走 API（SSRF 防护 + 原文存档 + 变更检测都在那边）；
4. **年度文档要记着换**：带年份的来源（「2025年统计公报」）跨年就过期，
   靠 `source-freshness` 体检发现；
5. **省级来源不要让每个城市重复人工搜** —— 同省城市直接复用。
