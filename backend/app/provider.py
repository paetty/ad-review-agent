from __future__ import annotations
import os, time
from dataclasses import dataclass
import httpx
from .engine import repair_model_output

class ProviderError(RuntimeError):
    def __init__(self, code: str, message: str): super().__init__(message); self.code=code

@dataclass
class ProviderResponse:
    data: dict
    provider: str
    model: str
    latency_ms: int
    input_tokens: int = 0
    output_tokens: int = 0

class OpenAICompatibleProvider:
    def __init__(self):
        self.api_key=os.getenv("LLM_API_KEY", ""); self.base_url=os.getenv("LLM_BASE_URL", "").rstrip("/"); self.model=os.getenv("LLM_MODEL", ""); self.provider=os.getenv("LLM_PROVIDER", "openai_compatible")
    @property
    def configured(self): return bool(self.api_key and self.base_url and self.model)
    async def generate(self, messages: list[dict], schema: dict) -> ProviderResponse:
        if not self.configured: raise ProviderError("validation_error", "Provider configuration incomplete")
        payload={"model":self.model,"messages":messages,"temperature":0,"response_format":{"type":"json_schema","json_schema":{"name":"ad_experience_analysis","strict":True,"schema":schema}}}
        thinking=os.getenv("LLM_ENABLE_THINKING", "").strip().lower()
        if thinking:
            if thinking not in {"true", "false"}:
                raise ProviderError("validation_error", "LLM_ENABLE_THINKING 必须为 true、false 或留空")
            payload["enable_thinking"]=thinking=="true"
        started=time.perf_counter()
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=25) as client:
                    response=await client.post(f"{self.base_url}/chat/completions",headers={"Authorization":f"Bearer {self.api_key}"},json=payload)
                if response.status_code==429:
                    if attempt<2: continue
                    raise ProviderError("provider_rate_limit", "模型服务限流，请稍后重试")
                response.raise_for_status()
                body=response.json(); usage=body.get("usage", {}); message=body["choices"][0]["message"]
                if message.get("refusal"):
                    raise ProviderError("provider_refusal", "模型拒绝处理该输入，请转人工复核")
                content=message.get("content")
                if not isinstance(content,str):
                    raise ProviderError("malformed_model_output", "模型未返回可解析的文本内容")
                return ProviderResponse(
                    data=repair_model_output(content),
                    provider=self.provider, model=body.get("model", self.model),
                    latency_ms=round((time.perf_counter()-started)*1000),
                    input_tokens=int(usage.get("prompt_tokens", 0) or 0),
                    output_tokens=int(usage.get("completion_tokens", 0) or 0),
                )
            except httpx.TimeoutException:
                if attempt==2: raise ProviderError("provider_timeout", "模型服务超时")
            except httpx.HTTPStatusError as exc:
                raise ProviderError("provider_error", f"模型服务返回 HTTP {exc.response.status_code}") from exc
            except ProviderError: raise
            except (KeyError, TypeError, ValueError) as exc: raise ProviderError("malformed_model_output", "模型输出无法解析") from exc

