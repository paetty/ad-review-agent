import assert from "node:assert/strict";
import path from "node:path";
import { pathToFileURL } from "node:url";
import test from "node:test";
const moduleUrl=process.env.PLAYWRIGHT_MODULE_PATH?pathToFileURL(path.join(process.env.PLAYWRIGHT_MODULE_PATH,"index.mjs")).href:"playwright";
const {chromium}=await import(moduleUrl);
const base=process.env.NAVIGATION_TEST_URL||"http://localhost:3000";
const backend=process.env.EVALUATION_TEST_API||"http://127.0.0.1:8015";
for(const url of [base,backend])if(!["localhost","127.0.0.1"].includes(new URL(url).hostname))throw Error("Local test only");

test("select dataset, preview, run rules and inspect persisted differences",{timeout:60000},async()=>{
 const browser=await chromium.launch({headless:true,channel:"chrome"});
 const page=await browser.newPage({viewport:{width:1440,height:1000}});
 page.setDefaultTimeout(10000);
 const errors=[];const requests=[];
 page.on("pageerror",e=>errors.push(e.message));
 // Proxy only to an isolated local DB/server. Provider starts are prohibited.
 await page.route("**/api/**",async route=>{
  const req=route.request();const u=new URL(req.url());
  requests.push({method:req.method(),path:u.pathname});
  if(req.method()==="POST"){
   assert.ok(["/api/evaluations/preview","/api/evaluations/runs"].includes(u.pathname));
   if(u.pathname.endsWith("/runs"))assert.equal(req.postDataJSON().mode,"rules");
  }
  const response=await route.fetch({url:backend+u.pathname+u.search});
  await route.fulfill({response});
 });
 try{
  await page.goto(base,{waitUntil:"networkidle"});
  await page.getByRole("button",{name:"评测中心",exact:true}).click();
  await page.getByRole("heading",{name:"统一评测中心",exact:true}).waitFor();
  const selector=page.getByLabel("评测数据集",{exact:true});
  await selector.selectOption("supplement");
  await page.getByRole("button",{name:"2. 预览条数与调用量",exact:true}).click();
  await page.getByText("预计模型逻辑调用：0次；最多HTTP尝试：0次。",{exact:true}).waitFor();
  await page.getByRole("button",{name:"3. 开始本次评测",exact:true}).click();
  await page.getByText(/进度：12\/12；调用失败：0条/).waitFor();
  await page.getByText("S01 ·",{exact:false}).first().waitFor();
  await page.getByLabel("只看不符合参考或调用失败").check();
  await page.getByText("S05 · 存在差异",{exact:false}).first().click();
  await page.getByRole("cell",{name:"素材不清晰、素材陈旧/过期",exact:true}).waitFor();
  await page.getByRole("button",{name:"单条分析",exact:true}).click();
  await page.getByRole("button",{name:"评测中心",exact:true}).click();
  assert.equal(await selector.inputValue(),"supplement");
  await page.getByText(/进度：12\/12；调用失败：0条/).waitFor();
  assert.equal(requests.filter(x=>x.method==="POST"&&x.path==="/api/evaluations/runs").length,1);
  await page.getByRole("button",{name:"查看逐条结果",exact:true}).first().click();
  await page.getByText(/进度：12\/12；调用失败：0条/).waitFor();
  await page.getByLabel("运行模式",{exact:true}).selectOption("provider");
  await page.getByRole("button",{name:"2. 预览条数与调用量",exact:true}).click();
  await page.getByText("预计模型逻辑调用：12次；最多HTTP尝试：36次。",{exact:true}).waitFor();
  assert.equal(await page.getByRole("button",{name:"3. 开始本次评测",exact:true}).isDisabled(),true);
  assert.deepEqual(errors,[]);
 }finally{await browser.close();}
});
