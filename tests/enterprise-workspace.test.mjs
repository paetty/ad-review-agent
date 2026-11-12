import assert from "node:assert/strict";
import { readFile, mkdir } from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
import test from "node:test";

const base = process.env.ENTERPRISE_TEST_FRONTEND || "http://localhost:3001";
const backend = process.env.ENTERPRISE_TEST_BACKEND || "http://localhost:8016";
if (![base, backend].every(value => new URL(value).origin === value && new URL(value).hostname === "localhost")) {
  throw Error("Requires local enterprise test URLs");
}
const credentialsPath = process.env.ENTERPRISE_TEST_CREDENTIALS;
if (!credentialsPath) throw Error("Use credentials from the isolated enterprise acceptance database.");
const passwords = new Map((await readFile(credentialsPath, "utf8")).trim().split(/\r?\n/).map(line => line.split("\t")));
const moduleUrl = process.env.PLAYWRIGHT_MODULE_PATH
  ? pathToFileURL(path.join(process.env.PLAYWRIGHT_MODULE_PATH, "index.mjs")).href : "playwright";
const { chromium } = await import(moduleUrl);

test("staff login, shared workspace, review attribution and industry references", {timeout: 110000}, async () => {
  const browser = await chromium.launch({headless:true, channel:"chrome"});
  const context = await browser.newContext({viewport:{width:1440,height:1000}});
  const page = await context.newPage();
  page.setDefaultTimeout(16000);
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  const heading = "让每一条反馈，都有清晰的处理路径";
  const nav = page.getByRole("navigation",{name:"主导航"});
  const login = async (id) => {
    assert.ok(passwords.has(id), "Missing isolated test account");
    await page.getByLabel("模拟工号").fill(id);
    await page.getByLabel("密码", {exact:true}).fill(passwords.get(id));
    await page.getByRole("button", {name:"登录工作台",exact:true}).click();
    await page.getByRole("heading", {name:heading,exact:true}).waitFor();
  };
  const logout = async () => {
    await page.getByRole("button", {name:"退出登录",exact:true}).click();
    await page.getByRole("button", {name:"登录工作台",exact:true}).waitFor();
  };
  const api = async (route, method = "GET", body) => {
    const response = await context.request.fetch(backend + "/api" + route, {
      method, data:body, headers:{Origin:base},
    });
    return {status:response.status(), body:await response.json().catch(()=>null)};
  };
  const screenshot = async (name) => {
    if (!process.env.ENTERPRISE_TEST_SCREENSHOTS) return;
    await mkdir(process.env.ENTERPRISE_TEST_SCREENSHOTS, {recursive:true});
    await page.screenshot({path:path.join(process.env.ENTERPRISE_TEST_SCREENSHOTS, name)});
  };
  try {
    await page.goto(base);
    for (const route of ["/analyses","/enterprise/dashboard","/evaluations/runs","/business/reports/sample/export"]) {
      assert.equal((await api(route)).status,401);
    }
    await page.getByLabel("模拟工号").fill("DEMO-OPS-01");
    await page.getByLabel("密码", {exact:true}).fill("invalid-password-for-test");
    await page.getByRole("button", {name:"登录工作台",exact:true}).click();
    await page.getByRole("alert").getByText("工号或密码错误").waitFor();
    await login("DEMO-OPS-01");
    const cookie = (await context.cookies(backend+"/api/auth/me")).find(item=>item.name==="ad_enterprise_session");
    assert.ok(cookie?.httpOnly && cookie.sameSite==="Lax" && cookie.expires > Date.now()/1000);
    assert.equal(await page.evaluate(()=>document.cookie.includes("ad_enterprise_session")),false);
    await page.reload();
    await page.getByRole("heading", {name:heading}).waitFor();
    assert.equal((await context.request.post(backend+"/api/auth/logout",{headers:{Origin:"https://example.test"}})).status(),403);
    const opsOverview = (await api("/enterprise/dashboard")).body;
    assert.ok(opsOverview.analysis_count>=12 && opsOverview.high_risk_count>0);
    const menu = await nav.getByRole("button").allTextContents();
    assert.ok(menu.includes("行业规范动态") && menu.includes("人工复核"));
    assert.equal(await page.getByRole("heading",{name:"行业规范动态",exact:true,level:3}).count(),0);
    await screenshot("operations.png");

    const title = "synthetic_demo · 企业验收 " + Date.now();
    await page.getByRole("button",{name:"＋ 新建分析",exact:true}).click();
    await page.getByLabel("素材标题",{exact:true}).fill(title);
    await page.getByLabel("用户反馈文本",{exact:true}).fill("浏览器提示落地页是恶意网站，广告自动跳转。");
    await page.getByRole("button",{name:"开始分析",exact:true}).click();
    await page.getByText("等待人工确认",{exact:true}).waitFor();
    await page.getByRole("button",{name:"接受并继续",exact:true}).click();
    await page.getByRole("heading",{name:"人工复核结果",exact:true}).waitFor();
    const agentRow = (await api("/analyses")).body.find(row=>row.input.title===title);
    assert.equal(agentRow.latest_review.reviewer,"DEMO-OPS-01");

    const pending = (await api("/analyses?pending_only=true")).body;
    const selected = pending.find(row=>["high","critical"].includes(row.output.overall_risk));
    assert.ok(selected, "Expected a seeded high-risk case awaiting review");
    const before = (await api("/enterprise/dashboard")).body.pending_review_count;
    await page.getByRole("navigation",{name:"主导航"}).getByRole("button",{name:"人工复核",exact:true}).click();
    await page.getByLabel("搜索复核记录").fill(selected.input.title);
    await page.getByRole("button",{name:"查看并复核",exact:true}).click();
    await page.getByRole("button",{name:"编辑修正版",exact:true}).click();
    const editor = page.getByRole("region",{name:"人工修正表单"});
    await editor.getByLabel("修改原因或备注",{exact:true}).fill("synthetic_demo 人工核查记录");
    await editor.getByLabel("处理建议",{exact:true}).first().fill("人工确认：核查触发跳转的页面行为。");
    await editor.getByRole("button",{name:"保存修正并继续",exact:true}).click();
    await page.getByText("人工版本已保存，AI 原始结果保留。",{exact:true}).waitFor();
    await page.getByText("复核工号 DEMO-OPS-01",{exact:true}).waitFor();
    assert.equal((await api("/enterprise/dashboard")).body.pending_review_count,before-1);
    // Even direct requests cannot impersonate a reviewer or increase the completed count.
    assert.equal((await api(`/analyses/${agentRow.id}/reviews`,"POST",{decision:"accepted",reviewer:"DEMO-LEAD-01"})).status,200);
    assert.equal((await api("/analyses")).body.find(row=>row.id===agentRow.id).latest_review.reviewer,"DEMO-OPS-01");
    assert.equal((await api("/enterprise/dashboard")).body.pending_review_count,before-1);

    const demoInput = await api("/business/demo-input");
    assert.equal(demoInput.status,200);
    const report = await api("/business/reports","POST",demoInput.body);
    assert.equal(report.status,200);
    const reportId = report.body.report_id;
    const caseId = report.body.cases[0].case_id;
    const reviewReport = await api(`/business/reports/${reportId}/cases/${caseId}/review`,"POST",{
      decision:"request_info", reviewer:"DEMO-PM-01", notes:"合成验收：需要补充核查证据",
    });
    assert.equal(reviewReport.status,200);
    assert.equal(reviewReport.body.cases[0].review_history.at(-1).reviewer,"DEMO-OPS-01");
    assert.equal((await context.request.get(backend+`/api/business/reports/${reportId}/export`)).status(),200);

    await logout();
    const revoked = await fetch(backend+"/api/auth/me",{headers:{Cookie:`ad_enterprise_session=${cookie.value}`}});
    assert.equal(revoked.status,401);
    await login("DEMO-PM-01");
    assert.deepEqual(await nav.getByRole("button").allTextContents(),menu);
    assert.equal(await page.getByText(title,{exact:true}).count(),0);
    const productRow = (await api("/analyses")).body.find(row=>row.id===selected.id);
    assert.deepEqual(productRow.output,selected.output);
    assert.equal(productRow.latest_review.reviewer,"DEMO-OPS-01");
    assert.equal(productRow.latest_review.corrected.strategy_recommendations[0].action,"人工确认：核查触发跳转的页面行为。");

    assert.equal((await api(`/analyses/${selected.id}`,"DELETE")).status,403);
    assert.equal((await api("/prompts/demo-v1.0/activate","POST")).status,403);
    assert.equal((await api("/experiment/assign","POST",{})).status,403);
    assert.equal((await api("/evaluation/run","POST")).status,403);
    assert.equal((await api(`/business/reports/${reportId}/export`)).status,200);
    await screenshot("product.png");
    await nav.getByRole("button",{name:"评测中心",exact:true}).click();
    await page.getByRole("heading",{name:"统一评测中心",exact:true}).waitFor();
    assert.ok((await api("/evaluations/runs")).body.length>=1);
    assert.equal((await api("/evaluations/preview","POST",{mode:"provider"})).status,403);
    assert.equal((await api("/evaluations/runs","POST",{mode:"provider",dataset_sha256:"0".repeat(64),confirm_provider:true})).status,403);
    const preview = await api("/evaluations/preview","POST",{mode:"rules",dataset:"supplement"});
    assert.equal(preview.status,200);
    assert.equal(preview.body.expected_model_calls,0);
    const run = await api("/evaluations/runs","POST",{mode:"rules",dataset:"supplement",dataset_sha256:preview.body.dataset.sha256});
    assert.equal(run.status,202);

    await logout();
    await login("DEMO-LEAD-01");
    await page.getByRole("heading",{name:"近 7 天分析风险趋势",exact:true}).waitFor();
    assert.deepEqual(await nav.getByRole("button").allTextContents(),menu);
    const summary = (await api("/enterprise/dashboard")).body;
    assert.equal(summary.pending_review_count,before-1);
    assert.equal(summary.trend.length,7);
    assert.deepEqual((await api("/overview")).body.risk_trends,summary);
    assert.equal((await api("/analyses")).status,200);
    assert.equal((await api("/prompts")).status,200);
    assert.equal((await api("/evaluations/runs")).status,200);
    assert.equal((await api("/business/reports/" + reportId)).status,200);
    assert.equal((await api("/business/reports/" + reportId + "/export")).status,200);
    assert.equal((await api("/analyses/" + selected.id,"DELETE")).status,403);
    await screenshot("shared-overview.png");
    await nav.getByRole("button",{name:"行业规范动态",exact:true}).click();
    await page.getByRole("heading",{name:"行业规范动态",exact:true,level:3}).waitFor();
    await page.getByRole("heading",{name:"互联网广告市场秩序整治重点任务",exact:true}).waitFor();
    assert.equal((await api("/enterprise/policy-watch")).body.length,4);
    await page.getByLabel("资料类型").selectOption("peer_platform");
    await page.getByRole("heading",{name:"华为广告 2026 年 9 月典型驳回案例",exact:true}).waitFor();
    assert.equal(await page.getByRole("heading",{name:"新人优惠资格核查",exact:true}).count(),0);
    await page.getByLabel("资料类型").selectOption("all");
    await screenshot("industry-watch.png");
    await logout();

    for (let attempt=0;attempt<5;attempt++) {
      assert.equal((await api("/auth/login","POST",{employee_id:"INVALID",password:"invalid-password"})).status,401);
    }
    assert.equal((await api("/auth/login","POST",{employee_id:"INVALID",password:"invalid-password"})).status,429);
    assert.deepEqual(errors,[]);
  } finally {
    await browser.close();
  }
});
