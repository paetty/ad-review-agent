import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request("http://localhost/", {
      headers: { accept: "text/html" },
    }),
    {
      ASSETS: {
        fetch: async () => new Response("Not found", { status: 404 }),
      },
    },
    {
      waitUntil() {},
      passThroughOnException() {},
    },
  );
}

test("server-renders the ad assistant shell", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /<title>广告素材体验分析与策略建议助手<\/title>/i);
  assert.match(html, /把分散反馈变成可追溯的策略闭环/);
  assert.match(html, /Deterministic Demo Mode/);
  assert.match(html, /AI 建议，仅供辅助判断/);
  assert.doesNotMatch(html, /LLM_API_KEY|sk-[a-z0-9_-]+/i);
});

test("keeps provider secrets server-side and exposes the guarded image flow", async () => {
  const [dashboard, api, envExample] = await Promise.all([
    readFile(new URL("../app/components/Dashboard.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/lib/api.ts", import.meta.url), "utf8"),
    readFile(new URL("../.env.example", import.meta.url), "utf8"),
  ]);
  assert.match(dashboard, /\/analyses\/image/);
  assert.match(dashboard, /image\/png,image\/jpeg,image\/webp/);
  assert.doesNotMatch(dashboard+api, /LLM_API_KEY|LLM_BASE_URL/);
  assert.match(envExample, /ENABLE_IMAGE_REVIEW=false/);
});
