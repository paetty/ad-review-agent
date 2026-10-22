# 真实模型与图片审核配置

项目使用 OpenAI-compatible `POST /v1/chat/completions`、Structured Outputs 和图片输入；本地 Markdown 规范由 TF-IDF 检索后作为可追溯上下文送入模型。API Key 只保存在后端 `.env`，不会返回浏览器。

OpenAI 官方参考：[API 认证与密钥安全](https://developers.openai.com/api/reference/overview)、[Chat Completions](https://developers.openai.com/api/reference/chat-completions/overview)、[Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=chat)、[模型比较](https://developers.openai.com/api/docs/models/compare)。

## 第 1 步：先配置文本模型

在项目根目录把 `.env.example` 复制为 `.env`，填写：

```dotenv
LLM_API_KEY=你的服务端密钥
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-6-luna
LLM_PROVIDER=openai
DEMO_MODE=false
ENABLE_IMAGE_REVIEW=false
ALLOW_PROVIDER_EVALUATION=false
```

`gpt-6-luna` 适合作为首次联调的低成本选择；若更看重复杂判断质量，可改为 `gpt-6.1-sol`。使用其他兼容服务时只替换 base URL、模型名、Provider 名和密钥，但该服务必须支持 Chat Completions 的 `json_schema` response format。

不要把密钥写入 `NEXT_PUBLIC_*`、前端代码或聊天消息。`.env` 已被 `.gitignore` 忽略。

## 第 2 步：启动并确认状态

```powershell
.venv\Scripts\pip.exe install -r backend\requirements.txt
.venv\Scripts\python.exe backend\run.py
```

另开一个终端启动前端：

```powershell
npm install
npm run dev
```

访问 `http://127.0.0.1:8000/api/health`。成功时应看到：

- `mode` 为 `provider`
- `provider_adapter_configured` 为 `true`
- `rag` 为 `local_tfidf`
- `model` 与 `.env` 一致

先在“单条分析”中只提交文字。结果底部应显示真实模型名，且 `simulated` 不再成立。若配置不完整，API 会返回 `provider_not_configured`，不会静默退回 Demo。

## 第 3 步：开启图片审核

确认所选模型支持图片输入，并确认图片可以发送给该 Provider 后，把：

```dotenv
ENABLE_IMAGE_REVIEW=true
```

重启后端，再上传一张不含真实个人信息的 PNG/JPEG/WebP 测试图。限制为 5MB；文件仅在请求内存中转换为 data URL，不写入项目磁盘。模型的图片证据会标记为 `source=image`，高风险仍经过规则升级和人工复核。

## 第 4 步：最后再跑真实模型批量评测

默认不要开启。固定评测集会产生约 80 次模型请求。确认预算后设置：

```dotenv
ALLOW_PROVIDER_EVALUATION=true
```

完成后及时改回 `false`。评测结果仍是合成集指标，不代表线上业务收益。
