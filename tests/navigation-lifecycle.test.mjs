import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath, pathToFileURL } from "node:url";

// Use an installed Playwright, or the existing workspace runtime; no downloads.
const playwrightModule = process.env.PLAYWRIGHT_MODULE_PATH
  ? pathToFileURL(path.join(process.env.PLAYWRIGHT_MODULE_PATH, "index.mjs")).href
  : "playwright";
const { chromium } = await import(playwrightModule);
const root = fileURLToPath(new URL("../", import.meta.url));
const baseUrl = process.env.NAVIGATION_TEST_URL || "http://localhost:3000";
if (!["localhost", "127.0.0.1", "[::1]"].includes(new URL(baseUrl).hostname)) {
  throw new Error("Navigation regression is restricted to a local application.");
}

async function launchBrowser() {
  if (existsSync(chromium.executablePath())) return chromium.launch({ headless: true });
  return chromium.launch({ headless: true, channel: "chrome" });
}

const scenarios = [
  { name: "switch review and policy pages after successful loading", delay: 0, fail: false },
  { name: "leave pages while loading requests are still pending", delay: 200, fail: false },
  { name: "switch pages when read-only API requests fail", delay: 0, fail: true },
];

for (const scenario of scenarios) {
  test(scenario.name, { timeout: 60000 }, async () => {
    const browser = await launchBrowser();
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    page.setDefaultTimeout(7000);
    const runtimeErrors = [];
    const unexpectedRequests = [];
    const readRequests = [];
    const consoleErrors = [];
    const visited = [];
    page.on("pageerror", error => runtimeErrors.push(error.message));
    page.on("console", message => { if (message.type() === "error") consoleErrors.push(message.text()); });
    // Every API call is intercepted. Tests never invoke models or modify records.
    await page.route("**/api/**", async route => {
      const request = route.request();
      const url = new URL(request.url());
      if (request.method() !== "GET") {
        unexpectedRequests.push({ method: request.method(), path: url.pathname });
        await route.abort();
        return;
      }
      readRequests.push(url.pathname);
      const responses = {
        "/api/health": { status: "ok", mode: "demo", synthetic_demo: true },
        "/api/overview": { today_analyses: 0, risk_distribution: { low: 0 }, review_rate: 0, average_latency_ms: 0 },
        "/api/analyses": [],
        "/api/prompts": [{ version: "navigation-fixture", name: "导航测试样例", content: "合成测试，不调用模型。", is_active: true }],
      };
      if (!(url.pathname in responses)) {
        unexpectedRequests.push({ method: request.method(), path: url.pathname });
        await route.abort();
        return;
      }
      if (scenario.delay && ["/api/analyses", "/api/prompts"].includes(url.pathname)) {
        await new Promise(resolve => setTimeout(resolve, scenario.delay));
      }
      if (scenario.fail && ["/api/analyses", "/api/prompts"].includes(url.pathname)) {
        await route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: { message: "模拟接口暂不可用" } }) });
        return;
      }
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(responses[url.pathname]) });
    });
    try {
      await page.goto(baseUrl, { waitUntil: "networkidle" });
      const steps = [
        ["人工复核", "人工复核队列", "/api/analyses"],
        ["知识库与配置", "知识库与配置", "/api/prompts"],
        ["项目说明与复盘", "个人作品复盘", null],
        ["人工复核", "人工复核队列", "/api/analyses"],
        ["工作台", "让每一条反馈，都有清晰的处理路径", "/api/overview"],
        ["知识库与配置", "知识库与配置", "/api/prompts"],
        ["项目说明与复盘", "个人作品复盘", null],
      ];
      for (const [button, heading, endpoint] of steps) {
        const response = endpoint && !scenario.delay && !visited.includes(button) && button !== "工作台"
          ? page.waitForResponse(r => new URL(r.url()).pathname === endpoint)
          : null;
        await page.getByRole("button", { name: button, exact: true }).click();
        await page.getByRole("heading", { name: heading, exact: true, level: 3 }).waitFor();
        if (response) await response;
        visited.push(button);
      }
      await page.waitForLoadState("networkidle");
      assert.deepEqual(runtimeErrors, [], "Client runtime errors during navigation");
      assert.deepEqual(unexpectedRequests, [], "Only expected read-only fixture API requests are allowed");
      assert.ok(readRequests.includes("/api/analyses") && readRequests.includes("/api/prompts"));
      assert.ok(!consoleErrors.some(message => /destroy is not a function|must not return anything besides|useEffect\(async/.test(message)), "Invalid effect cleanup was reported");
    } finally {
      const artifact = path.join(root, ".tmp", "navigation-lifecycle");
      await mkdir(artifact, { recursive: true });
      await writeFile(path.join(artifact, scenario.name.replace(/\W+/g, "-") + ".json"), JSON.stringify({
        scenario: scenario.name, base_url: baseUrl, visited, runtime_errors: runtimeErrors,
        console_errors: consoleErrors, unexpected_requests: unexpectedRequests,
        intercepted_read_requests: readRequests, model_calls: 0,
      }, null, 2));
      await browser.close();
    }
  });
}

