# Ad Review Agent｜广告体验分析助手

这是一个可本地运行的广告治理个人项目。它把用户反馈整理成问题标签、风险、原话依据和核查建议，支持人工修正和报告导出。运营也可以上传广告日指标，检查异常或观察策略上线前后的变化。

## 当前工作台

| 模块 | 功能 |
| --- | --- |
| 工作台 | 查看累计分析和风险分布。企业演示还提供近 7 天风险趋势。 |
| 分析任务 | 新建分析、批量任务、按广告汇总、交接报告。新建分析可选择快速分析或分析并人工确认。 |
| 监测与策略 | 日常安全检测筛选高曝光素材、识别文字风险并比较反馈事件率。策略效果检测按指定前后周期比较反馈目标、收入和 eCPM 等护栏。 |
| 人工复核 | 核对依据，修改标签、风险和建议，保留原始结果。 |
| 评测中心 | 预览调用量、运行评测并查看逐条差异。企业演示仅开放规则基线。 |
| 知识库与配置 | 查看标签、参考资料和 Prompt 版本。普通模式可管理 Prompt，企业演示为只读。 |
| 行业规范动态 | 按类型和日期浏览人工整理的资料及来源。资料列表独立于 RAG 知识库。 |

演示时可在「监测与策略」运行[日常安全检测和策略效果检测](docs/ad-diagnostics-prompts.md)的合成案例。要展示从反馈到交付的完整流程，可进入「分析任务 → 交接报告」，运行配套案例，核查问题单后[导出报告](docs/mvp-business-guide.md)。

## 本地启动

需要 Node.js 22.13+、Python 3.11+ 和 pnpm。Windows PowerShell 在项目根目录运行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
.\.venv\Scripts\python.exe backend/run.py
```

另开一个终端：

```powershell
pnpm install --frozen-lockfile
pnpm dev
```

普通工作台通常在 [localhost:3000](http://localhost:3000/)，接口文档在 [127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)。[企业演示指南](docs/enterprise-workspace-mvp.md)提供模拟工号登录方式，使用 3001／8016 端口和独立 SQLite 数据库。

使用 Docker 时，首次运行可在 PowerShell 执行 `Copy-Item .env.example .env` 创建配置，再执行 `docker compose up --build`。保留已有的本机配置。

GitHub 提供源码和说明，交互演示在本地启动。旧界面见[历史截图档案](docs/screenshots/README.md)。

## 实现与运行边界

- React / vinext 前端调用 FastAPI，SQLite 保存分析、复核、报告和评测。规则引擎与本地 TF-IDF 检索提供分析依据，兼容模型适配层支持结构化响应。资料来源见[规则与数据集](docs/sources-and-datasets.md)。
- LangGraph 管理「分析并人工确认」的校验、检索、分析和人工暂停。需要复核的任务由人接受或修改后继续。暂停状态保存在进程内存中。正式报告须完成必要核查，投放和回滚决策由人工执行。
- 普通分析默认使用规则演示模式。图片在演示模式下用于基础检查和素材匹配，视觉分析需单独启用并配置兼容模型。配置步骤见[模型配置指南](docs/model-setup.md)。
- 「监测与策略」由程序计算指标、告警和护栏。配置模型后提交分析要求可触发条件提取和摘要，合成示例也适用。原始 CSV 与素材原文在本地处理。策略前后对比用于观察变化，因果判断需要对照验证。
- [评测中心](docs/evaluation-center-guide.md)支持 28 条开发、8 条验证、12 条补充开发和 80 条旧回归样例。真实评测须预览并确认调用量。[五条开发样例的真实模型复测](docs/model-pilot-retest-2026-10-23.md)记录两轮四项同时匹配 4/5 和 5/5 的结果。

项目使用公开资料、合成样例和脱敏输入，定位为个人原型。合成评测用于验证已知场景，线上业务收益仍待验证。

## 开发与验证

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests -q
pnpm lint
pnpm build
pnpm test
```

详见[架构说明](docs/architecture.md)、[贡献指南](CONTRIBUTING.md)、[安全说明](SECURITY.md)和 [MIT 许可证](LICENSE)。
