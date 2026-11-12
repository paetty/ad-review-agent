# 模拟企业工作台

所有模拟员工登录后进入同一个广告治理空间，使用统一的首页、菜单和接口权限。工号用于登录和复核留痕。预置示例使用本地合成数据。企业演示的常规分析与评测使用规则模式。「监测与策略」独立处理自然语言要求，配置模型后提交检测（包括合成示例）可触发条件提取和摘要。指标与护栏由程序计算。详见[检测说明](ad-diagnostics-prompts.md)。

## 本地启动

在 PowerShell 进入项目目录，已安装的项目依赖可以复用。先生成样本和账号，再启动独立后端。

```powershell
Set-Location 'D:\Projects\ad-assistant'
.\.venv\Scripts\python.exe -X utf8 backend/run_enterprise.py --init
.\.venv\Scripts\python.exe -X utf8 backend/run_enterprise.py
```

初始化会写入并打印以下三组固定演示凭据，同时生成 12 条近 7 日合成样本和一轮规则基线评测。重复执行会保留业务记录和已使用固定密码的会话。旧版的随机密码会被替换，对应的旧会话会失效。需要主动撤销三个演示账号的会话时，执行 `--init --reset-passwords`。

| 模拟工号 | 固定演示密码 |
| --- | --- |
| `DEMO-PM-01` | `DemoPM!2026` |
| `DEMO-OPS-01` | `DemoOPS!2026` |
| `DEMO-LEAD-01` | `DemoLead!2026` |

这三组公开凭据仅供本机合成数据演示。SQLite 中保存的是带盐的密码哈希。

打开另一个 PowerShell 窗口。

```powershell
Set-Location 'D:\Projects\ad-assistant'
$env:NEXT_PUBLIC_ENTERPRISE_DEMO='1'
$env:NEXT_PUBLIC_API_URL='http://localhost:8016/api'
npm run dev -- --host localhost --port 3001
```

浏览 [企业工作台](http://localhost:3001/)。前端与后端都以 `localhost` 为浏览器访问主机，后端监听本机 8016。登录所用 Cookie 需要同一站点，写请求只接受精确的本地前端来源 `http://localhost:3001`。端口被占用时，需要一起调整启动端口、`FRONTEND_ORIGIN` 与前端 API 配置。

演示数据位于 `data/enterprise-demo.sqlite3`。服务直接使用独立的企业数据库，原来在 8000 端口运行的模式可以并行使用自己的数据库。两个前端应分别用独立的启动终端设置环境。

## 统一工作台与访问范围

三个演示账号均可访问分析、监测与策略、复核、交接报告及其导出、规则基线评测、只读知识库和行业规范动态。未登录访问企业演示业务接口返回 401。企业演示统一锁定 Prompt 新建及切换、删除分析、匿名分桶、旧评测写入口和真实模型评测。按数据申请访问的流程留待后续确认。

密码使用带随机盐的 scrypt 哈希。随机会话标识保存在 HttpOnly Cookie，服务端仅保存其摘要，8 小时过期，退出时立即删除。登录按来源地址进行进程内限速，同一个窗口中最多允许 5 次失败尝试，窗口为 60 秒。员工提交普通复核、Agent 复核和交接报告复核时，后端用登录工号落库。前端退出会卸载已访问的页面，清除草稿和本次结果。

## 现场演示

1. 用任意演示账号登录。工作台保留累计指标、风险分布和任务入口，向下滚动查看近 7 天风险趋势。
2. 打开人工复核队列，核查一条高风险记录。保存后可查看复核工号，并展开 AI 原始结果。
3. 返回工作台并刷新统计，确认待复核数减少 1。换一个工号登录，核对菜单和分析数据一致。
4. 点击侧栏「行业规范动态」，按资料类型及近一周、近半年或近一年组合筛选。自定义区间支持拖动起止日期和直接选择日期，按 UTC+8 的自然日计算。仅标注月份的资料按整月覆盖范围匹配，生效日期在卡片内单列，未标注发布日期的资料可单独查看。

近 7 天按 UTC+8 的自然日统计，缺少记录的日期补零。“当前待复核分析数”统计全部原始分析中尚无已完成复核的记录，同一记录多次复核只计一次完成。交接报告的问题单使用独立状态和统计。工作台缺少同口径曝光分母时，反馈率显示为不可计算。

行业规范动态由人工整理更新，资料保存在 `data/enterprise/policy-watch.json`，分为监管资料、同业审核参考和内部模拟规范。发布方资料保留原文链接，模拟资料显著标记。提醒由人工评估适用性，与 RAG 检索库分开。

## 验证

- 现有模式的回归检查可运行 `python -m pytest backend/tests -q`、`npm run lint`、`npm run build`、`npm test`。
- 浏览器验收运行 `npm run test:enterprise`。需要本地 Chrome 和 Playwright。可用 `PLAYWRIGHT_MODULE_PATH` 指向 Playwright 安装目录。必须用独立验收数据库，设置 `ENTERPRISE_DEMO_DB` 为项目 `.tmp/` 下新建的 `.sqlite3` 文件，再执行初始化并将输出保存在忽略目录。设置 `ENTERPRISE_TEST_CREDENTIALS` 为该文件，启动同一独立数据库对应的 8016 后端和 3001 前端。验收会创建分析、报告、评测和复核记录，最后验证登录限速。可选用 `ENTERPRISE_TEST_SCREENSHOTS` 保存合成截图。使用独立端口时，设置 `ENTERPRISE_TEST_FRONTEND` 和 `ENTERPRISE_TEST_BACKEND` 为对应的 localhost 地址。

范围为单机本地演示、三个员工账号和一个共享空间。真实企业员工核验、SSO、组织架构、跨部门数据隔离、自动监测外部规范和公开部署留待后续。Agent 暂停状态沿用原有进程内存检查点，已保存的分析和复核记录在 SQLite 中保留。
