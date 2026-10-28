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
        ["Prompt 与规则", "Prompt、标签与演示规范", "/api/prompts"],
        ["项目复盘", "个人作品复盘", null],
        ["人工复核", "人工复核队列", "/api/analyses"],
        ["项目概览", "把分散反馈变成可追溯的策略闭环", "/api/overview"],
        ["Prompt 与规则", "Prompt、标签与演示规范", "/api/prompts"],
        ["项目复盘", "个人作品复盘", null],
      ];
      for (const [button, heading, endpoint] of steps) {
        const response = endpoint && !scenario.delay && !visited.includes(button) && button !== "项目概览"
          ? page.waitForResponse(r => new URL(r.url()).pathname === endpoint)
          : null;
        await page.getByRole("button", { name: button, exact: true }).click();
        await page.getByRole("heading", { name: heading, exact: true }).waitFor();
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

test("forms, completed agent results and pending business requests survive navigation", {timeout:60000}, async()=>{
 const browser=await launchBrowser();
 const page=await browser.newPage({viewport:{width:1440,height:1000}});
 page.setDefaultTimeout(8000);
 const errors=[];page.on("pageerror",e=>errors.push(e.message));
 let agentCalls=0,businessCalls=0,release;
 const delayed=new Promise(resolve=>{release=resolve});
 const output={analysis_id:"synthetic-navigation",labels:[{label:"return_path_friction",confidence:.8}],overall_risk:"high",confidence:.8,evidence:[],citations:[],strategy_recommendations:[],requires_human_review:true,uncertainties:[],model_info:{provider:"fixture",model:"no-real-model",latency_ms:1,input_tokens:0,output_tokens:0,estimated_cost_usd:0,simulated:true},prompt_version:"test",assessment_status:"issue_detected"};
 await page.route("**/api/**",async route=>{
  const request=route.request(),pathname=new URL(request.url()).pathname;
  let body;
  if(pathname==="/api/health")body={mode:"demo"};
  else if(pathname==="/api/overview")body={risk_distribution:{low:0},today_analyses:0};
  else if(pathname==="/api/agent/runs"&&request.method()==="POST"){
   agentCalls++;body={thread_id:"synthetic-thread",status:"awaiting_review",output,trace:[],interrupt:{reason:"合成等待人工"}};
  }else if(pathname==="/api/business/demo-input")body={synthetic:true};
  else if(pathname==="/api/business/reports"&&request.method()==="POST"){
   businessCalls++;await delayed;
   body={report_id:"synthetic-report",dataset_source:"synthetic",elapsed_ms_measured:1,metric_boundary:"合成测试",summary:{feedback_rows:6,cases:0,pending_review:0,human_reviewed:0,handoff_ready:true},cases:[]};
  }else throw Error("Unexpected API "+pathname);
  await route.fulfill({status:200,contentType:"application/json",body:JSON.stringify(body)});
 });
 try{
  await page.goto(baseUrl,{waitUntil:"networkidle"});
  await page.getByRole("button",{name:"Agent 工作台",exact:true}).click();
  const title=page.locator('section:not([hidden]) input:visible').first();
  await title.fill("保留输入的合成测试");
  await page.getByRole("button",{name:"启动Agent任务",exact:true}).click();
  await page.getByText("合成等待人工",{exact:true}).waitFor();
  await page.getByRole("button",{name:"单条分析",exact:true}).click();
  await page.getByRole("heading",{name:"单条体验诊断",exact:true}).waitFor();
  await page.getByRole("button",{name:"Agent 工作台",exact:true}).click();
  assert.equal(await title.inputValue(),"保留输入的合成测试");
  await page.getByText("合成等待人工",{exact:true}).waitFor();
  assert.equal(agentCalls,1);
  await page.getByRole("button",{name:"业务闭环",exact:true}).click();
  const requestStarted=page.waitForRequest(r=>new URL(r.url()).pathname==="/api/business/reports");
  await page.getByRole("button",{name:"运行配套模拟案例",exact:true}).click();
  await requestStarted;
  await page.getByRole("button",{name:"单条分析",exact:true}).click();
  release();
  await page.getByRole("button",{name:"业务闭环",exact:true}).click();
  await page.getByText("来源：synthetic；本次实测处理耗时 1ms。耗时包含当前分析流程，不代表已测真实模型。",{exact:true}).waitFor();
  assert.equal(businessCalls,1);
  assert.deepEqual(errors,[]);
 }finally{release();await browser.close();}
});
