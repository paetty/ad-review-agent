# Ad Review Agent｜广告体验审核智能体

Ad Experience Insight Assistant 是面向广告商业化产品经理、体验治理、内容审核和运营人员的个人作品。它把素材说明与用户反馈转换为统一标签、风险等级、可追溯证据和结构化策略建议，并支持批量处理、人工复核、Prompt 版本、合成评测与匿名实验分桶。

项目新增了一个**有边界的 LangGraph Agent 工作流**：输入校验 → 本地规则检索 → 风险分析 → 条件路由。低风险自动完成，高风险会暂停并等待人工接受或修改后再继续。Agent 只负责分析和建议，不执行下线、处罚或投放修改。

“综合归因”支持上传包含 `ad_id`、`feedback`、`image_filename` 等字段的 CSV，并同时上传对应素材图片。系统会按广告 ID 聚合多条反馈，输出主因分布、风险等级、证据、建议、素材匹配情况与人工复核状态。Demo 模式只检查图片格式、大小和分辨率，不宣称已完成 OCR 或图片语义识别。

> 事实边界：本项目不接入 vivo 内部系统，不使用公司内部数据，也不声称产生真实 CTR、收入或体验提升。知识库分别标记自编演示规范、公开官方资料摘要和内部模拟规范；公开研究评论仅作为待标注候选，不当作本项目金标。

## 当前建议演示：业务闭环

进入“业务闭环”，可一键运行6条反馈与配套曝光案例，或上传两张UTF-8 CSV（页面提供模板）。系统按广告、素材、场景、平台和时间窗关联曝光；缺失、零分母与抽样覆盖不计算总体比率。输出问题单、用户原话、规则来源、缺失证据、责任团队及建议。

高风险/证据不足/需核查素材的条目进入人工复核，可以实际编辑标签和风险并记录备注。尚有待核查条目时只允许导出草稿；必要核查完成后才允许导出交接报告。导出不发送消息，也不修改投放。详见 [最小业务方案](docs/mvp-business-guide.md)。

来源登记见 [规则与数据集](docs/sources-and-datasets.md)，分组隔离与冻结要求见 [独立评测协议](docs/blind-evaluation-protocol.md)。

最新迭代见 [修复清单与后续优化策略](docs/optimization-strategy.md)：区分证据不足、未见明确问题与免责声明，保留未采纳模型候选；使用历史真实响应离线回放验证后处理，不把开发回归当作独立模型准确率。

修复后的[五条真实模型复测](docs/model-pilot-retest-2026-10-23.md)已完成：本轮四项同时匹配5/5，另一次同版本为4/5；保留全部结果，不宣称总体准确率100%。

2026-10-28更新：新增[统一评测中心](docs/evaluation-center-guide.md)，可选择28条开发、8条验证、12条补充开发或80条旧版回归数据，预览调用量后再运行。真实调用需显式确认；评测历史与业务分析记录隔离保存。Agent支持实际修改标签、风险和建议，并保留AI原文；菜单切换保留本次页面状态，刷新后的持久化范围见对应说明。

## 快速启动

要求 Node.js 22.13+、Python 3.11+。

```bash
python -m venv .venv
.venv/Scripts/pip install -r backend/requirements.txt
.venv/Scripts/python backend/run.py

# 新终端
npm install
npm run dev
```

打开前端输出的本地地址（通常为 `http://localhost:3000`）；API 文档位于 `http://127.0.0.1:8000/docs`。

也可以使用 Docker：

```bash
copy .env.example .env
docker compose up --build
```

启动后进入“Agent 工作台”。提交普通反馈会直接完成；提交“强制跳转、无法关闭、疑似诈骗”等高风险反馈，会看到工作流暂停和人工复核按钮。Agent API 为 `POST /api/agent/runs`，流程说明为 `GET /api/agent/graph`。

## Agent 是怎样工作的

```mermaid
flowchart LR
  A[输入与隐私校验] --> B[本地 TF-IDF 规则检索]
  B --> C[规则引擎或兼容模型分析]
  C --> D{是否需要人工复核}
  D -->|否| E[完成并保存]
  D -->|是| F[暂停等待人工]
  F --> E
```

- LangGraph 管理节点、状态、条件分支和人工中断；这是一条可解释的审核工作流，不是可以任意调用外部系统的全自动 Agent。
- 默认使用内存检查点，适合本地演示；服务重启后，尚未完成的 Agent 任务不会保留。生产化需换成持久化 checkpointer。
- 本地 RAG 返回真实规则片段和 `citation_id`；模型输出无法引用本次检索之外的规则。
- 当前 Agent 工作台处理文本审核；已有图片上传与综合归因仍通过独立接口运行，视觉语义分析只有在配置兼容视觉模型后才会启用。

## Demo Mode 与 Provider

复制 `.env.example` 为 `.env`。默认 `DEMO_MODE=true`，无需 API Key：关键词、风险规则和固定模板会产生可重复结果；耗时与 Token 字段为确定性模拟值，`simulated=true`，费用为 0。它与真实 Provider 共用 Pydantic schema，但不代表真实模型效果，也不进行视觉理解。

Provider Adapter 从后端环境变量读取 `LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL` 和 `LLM_PROVIDER`，不硬编码厂商或模型。设置 `DEMO_MODE=false` 后，真实 Provider 会消费本地 TF-IDF RAG 的可追溯片段，并经过 JSON Schema 校验、引用过滤、否定感知规则兜底与风险升级。配置不完整时会明确报错，不会静默伪装成真实模型。密钥不会返回前端、写入导出或普通日志。

图片审核支持 PNG/JPEG/WebP（最大 5MB），图片只在请求内存中处理，不写入磁盘。真实视觉审核还需显式设置 `ENABLE_IMAGE_REVIEW=true`，并使用支持图片输入的兼容模型；Demo 模式只记录“未完成视觉理解”并强制人工复核。真实模型批量评测默认关闭，避免意外产生 80 次调用费用。

逐步配置见 [`docs/model-setup.md`](docs/model-setup.md)。

## 数据、安全与验证

- CSV 仅允许白名单字段、UTF-8、最大 2MB；模板见 `sample-data/batch-template.csv`。
- 检测 IMEI、手机号、姓名、身份证、邮箱、设备标识字段；正文敏感模式也会阻止处理。
- critical 必须人工复核；病毒、恶意网站、诈骗、隐私风险会建议暂停自动放量并核查。
- 人工修正作为新记录保存，不覆盖 AI 原始输出；分析记录可删除。

```bash
.venv/Scripts/python -m pytest backend/tests -q
npm run lint
npm run build
npm test
```

后端业务验收覆盖分母匹配、复核实际修改、原始结果保留、正式导出门禁及平台规则范围。请以你本机最新一次测试输出为准，不把合成数据成绩表述为线上业务效果。

页面生命周期回归可运行`npm run test:navigation`（需先启动本地前端，并提供已安装的Playwright/浏览器）。它拦截所有API，不消耗模型额度；正常、慢响应和接口失败三种页面切换场景均验证。配置方式与修复记录见[页面切换修复](docs/frontend-navigation-fix.md)。

运行评测：启动前后端，在“评测中心”选择28条开发集、8条验证集、12条补充集或80条旧版回归集，再选择规则基线/真实模型，预览调用量后执行。真实模式需显式确认；进度、逐条差异和历史记录保存于独立评测表，不计入业务分析量。命令行统一入口为 `scripts/run_evaluation.py`，详见 [统一评测指南](docs/evaluation-center-guide.md)。旧固定80条接口仍保留兼容，但不再是前端默认入口。

## 目录

```text
app/                         前端页面与组件
backend/app/                 FastAPI、模型、检索、规则与 Provider
backend/tests/               后端验收测试
data/policies/               11份：7演示规范、3公开来源摘要、1内部模拟规范（22片段）
data/synthetic_records.json  116 条合成记录（80 评测）
data/evaluation/             单人复核合成数据：48条v2（28开发、8验证、12留出候选）及12条补充开发案例；不是独立盲测
docs/                        产品、架构、评测、安全与面试材料
sample-data/                 CSV 模板
scripts/                     合成数据生成脚本
.github/                     CI、Issue 模板
```

截图建议放到 `docs/screenshots/`，命名 `overview.png`、`single-analysis.png`、`evaluation.png`。本项目不包含伪造的官方截图、Logo 或内部界面。“AI 建议，仅供辅助判断”。

## 参与项目

本地开发与提交规范见 [`CONTRIBUTING.md`](CONTRIBUTING.md)，安全问题见 [`SECURITY.md`](SECURITY.md)，社区约定见 [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md)。项目采用 [`MIT License`](LICENSE)。

