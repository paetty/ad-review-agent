import assert from "node:assert/strict";
import path from "node:path";
import { pathToFileURL } from "node:url";
import test from "node:test";

const moduleUrl=process.env.PLAYWRIGHT_MODULE_PATH?pathToFileURL(path.join(process.env.PLAYWRIGHT_MODULE_PATH,"index.mjs")).href:"playwright";
const {chromium}=await import(moduleUrl);
const backend=process.env.EVALUATION_TEST_API||"http://127.0.0.1:8015";
const base=process.env.NAVIGATION_TEST_URL||"http://localhost:3000";
if(new URL(backend).port!=="8015"||![base,backend].every(x=>["127.0.0.1","localhost"].includes(new URL(x).hostname)))throw Error("Requires isolated local backend on 8015");

test("real rules API supports unified pause/resume and queue correction without model calls",{timeout:60000},async()=>{
 const health=await (await fetch(backend+"/api/health")).json();assert.equal(health.mode,"demo");
 const browser=await chromium.launch({headless:true,channel:"chrome"});
 const page=await browser.newPage({viewport:{width:1440,height:1000}});page.setDefaultTimeout(12000);
 const errors=[];page.on("pageerror",e=>errors.push(e.message));
 await page.route("**/api/**",async route=>{const u=new URL(route.request().url());const response=await route.fetch({url:backend+u.pathname+u.search});await route.fulfill({response});});
 try{
  await page.goto(base,{waitUntil:"networkidle"});
  await page.getByRole("button",{name:"分析任务",exact:true}).click();
  await page.getByRole("textbox",{name:"素材标题",exact:true}).fill("synthetic/demo 真实接口走查");
  await page.getByRole("textbox",{name:"用户反馈文本",exact:true}).fill("进入商品页后，返回很多次才能回到天气页。");
  await page.getByText("补充素材信息（可选）",{exact:true}).click();
  await page.getByRole("textbox",{name:"视频前 3 秒描述",exact:true}).fill("");
  await page.getByRole("button",{name:"开始分析",exact:true}).click();
  await page.getByText("等待人工确认",{exact:true}).waitFor();
  await page.getByRole("button",{name:"接受并继续",exact:true}).click();
  await page.getByRole("heading",{name:"人工复核结果",exact:true}).waitFor();
  await page.getByRole("button",{name:"人工复核",exact:true}).click();
  await page.getByRole("textbox",{name:"搜索复核记录"}).fill("真实接口走查");
  await page.getByRole("button",{name:"查看并复核",exact:true}).first().click();
  await page.getByRole("button",{name:"编辑修正版",exact:true}).click();
  const editor=page.getByRole("region",{name:"人工修正表单"});
  await editor.getByRole("textbox",{name:"修改原因或备注",exact:true}).fill("synthetic/demo 已核对返回路径反馈");
  await editor.getByRole("textbox",{name:"处理建议",exact:true}).first().fill("人工确认：优化返回路径，减少连续返回次数。");
  await editor.getByRole("button",{name:"保存修正并继续",exact:true}).click();
  await page.getByText("人工版本已保存，AI 原始结果保留。",{exact:true}).waitFor();
  await page.getByText("人工确认：优化返回路径，减少连续返回次数。",{exact:true}).waitFor();
  assert.deepEqual(errors,[]);
 }finally{await browser.close();}
});
