# 系统架构

## 有边界的 Agent 工作流

```mermaid
stateDiagram-v2
  [*] --> validate_input
  validate_input --> retrieve_policy
  retrieve_policy --> analyze_risk
  analyze_risk --> finalize: 无需人工复核
  analyze_risk --> human_review: 高风险或低置信度
  human_review --> finalize: 人工接受或标记修改
  finalize --> [*]
```

LangGraph 保存任务状态并负责条件路由。`human_review` 使用 interrupt 暂停执行，只有显式人工决定后才恢复。当前使用进程内检查点，定位是可运行的本地 Demo；生产部署应改用持久化检查点并增加鉴权、审计和并发控制。

```mermaid
flowchart LR
  A["输入校验"] --> B["PII / 敏感字段检测"] --> C["规则引擎预判"]
  C --> D["Query 构造 / 改写"] --> E["本地政策 Top-K 检索"] --> F["结构化 Prompt"]
  F --> G["Provider Adapter / Demo Engine"] --> H["JSON Schema 校验"]
  H -->|"失败一次"| I["单次修复"] --> H
  H --> J["规则后处理与风险升级"] --> K["SQLite 保存"] --> L["人工复核"] --> M["评测与版本比较"]
```

```mermaid
flowchart TB
  UI["Next.js App Router UI"] --> API["FastAPI"]
  API --> SAFETY["Validation + PII Guardrail"]
  API --> RAG["TF-IDF Retriever"] --> KB["Markdown Policy KB"]
  API --> ADAPTER["Provider Adapter"] --> DEMO["Deterministic Demo Engine"]
  ADAPTER -. "可配置" .-> LLM["OpenAI-compatible API"]
  API --> DB["SQLite + SQLAlchemy"]
  API --> EVAL["scikit-learn Evaluation"]
```

## ER 图

```mermaid
erDiagram
  analyses ||--o{ analysis_labels : contains
  analyses ||--o{ evidence_chunks : cites
  analyses ||--o{ recommendations : suggests
  analyses ||--o{ human_reviews : reviewed_as
  evaluation_runs ||--o{ evaluation_items : contains
  analyses { string id PK
    json input_json
    json original_output_json
    string overall_risk
    float confidence
    boolean requires_human_review
  }
  prompt_versions { int id PK
    string version UK
    text content
    boolean is_active
  }
  experiment_assignments { int id PK
    string anonymous_id_hash UK
    int bucket
    string group_name
  }
```

## 关键决策

- 字符 TF-IDF 对中文短反馈离线、确定、无需分词；Embedding 是 P1。
- 无密钥 Demo 与 Provider 共用 schema；不绑定模型。
- no_issue 互斥，风险只升级，critical 强制复核。
- citation_id 只能映射本次真实 chunk；无证据返回空引用。
- AI 原始输出不可变，人工修正版独立保存。
- 错误分类：validation_error、retrieval_error、provider_timeout、provider_rate_limit、malformed_model_output、policy_guardrail_triggered、unknown_error。超时/限流有限重试，结构修复仅一次。
- Agent 权限边界：只读规则、生成分析、保存分析与人工决定；不连接广告投放或处罚执行系统。

