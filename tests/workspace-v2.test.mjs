import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
import test from "node:test";

const moduleUrl = process.env.PLAYWRIGHT_MODULE_PATH ? pathToFileURL(path.join(process.env.PLAYWRIGHT_MODULE_PATH, "index.mjs")).href : "playwright";
const { chromium } = await import(moduleUrl);
const base = process.env.NAVIGATION_TEST_URL || "http://localhost:3000";
if (!["localhost", "127.0.0.1"].includes(new URL(base).hostname)) throw Error("Local test only");
const recommendation = {category:"product",action:"优化返回路径，减少连续返回次数",rationale:"反馈报告多次返回",priority:"P1",expected_metric:"返回成功率",guardrail_metric:"误触返回率"};
const output = {analysis_id:"synthetic-ui-v2",labels:[{label:"return_path_friction",confidence:.8}],overall_risk:"high",confidence:.8,evidence:[{source:"input",field:"feedback",quote:"返回很多次"}],citations:[{citation_id:"C1",document_title:"返回体验演示规范",snippet:"需要连续多次返回，属于返回路径摩擦。",score:.3,source_type:"synthetic_demo"}],strategy_recommendations:[recommendation],requires_human_review:true,uncertainties:[],model_info:{provider:"fixture",model:"synthetic-no-model",latency_ms:1,input_tokens:0,output_tokens:0,estimated_cost_usd:0,simulated:true},prompt_version:"fixture",assessment_status:"issue_detected"};

async function setup(viewport={width:1440,height:1000}) {
 const browser=await chromium.launch({headless:true,channel:"chrome"});
 const page=await browser.newPage({viewport});page.setDefaultTimeout(9000);
 const errors=[];const calls=[];let release;
 const delayed=new Promise(resolve=>{release=resolve});
 page.on("pageerror",e=>errors.push(e.message));
 await page.route("**/api/**",async route=>{
  const req=route.request(),pathname=new URL(req.url()).pathname;
  calls.push({path:pathname,method:req.method(),body:req.method()==="POST"&&!pathname.endsWith("/image")?req.postData():null});
  let body;
  if(pathname==="/api/health")body={mode:"demo",status:"ok"};
  else if(pathname==="/api/overview")body={risk_distribution:{low:0,medium:0,high:0,critical:0},today_analyses:0,average_latency_ms:0};
  else if(pathname==="/api/analyses"&&req.method()==="GET")body=[{id:output.analysis_id,input:{feedback:"合成反馈：返回很多次",title:"synthetic/demo",media_scene:"天气"},output}];
  else if(pathname==="/api/agent/runs")body={thread_id:"synthetic-thread",status:"awaiting_review",output,trace:[{node:"retrieve_policy",detail:"检索到合成规范"}],interrupt:{reason:"合成等待人工"}};
  else if(pathname==="/api/agent/runs/synthetic-thread/resume"){
   const edit=req.postDataJSON();const corrected={...output,labels:(edit.corrected_labels||output.labels.map(x=>x.label)).map(label=>({label,confidence:1})),overall_risk:edit.corrected_risk||output.overall_risk,strategy_recommendations:edit.edited_recommendations||output.strategy_recommendations};
   body={thread_id:"synthetic-thread",status:"completed",output,corrected_output:corrected,human_decision:edit,trace:[]};
  }else if(pathname===`/api/analyses/${output.analysis_id}/reviews`){
   const edit=req.postDataJSON();body={analysis_id:output.analysis_id,original:output,corrected:{...output,strategy_recommendations:edit.edited_recommendations||output.strategy_recommendations},decision:edit.decision};
  }else if(pathname==="/api/analyses"&&req.method()==="POST")body=output;
  else if(pathname==="/api/business/demo-input")body={synthetic:true};
  else if(pathname==="/api/business/reports"){
   await delayed;body={report_id:"synthetic-report",dataset_source:"synthetic",elapsed_ms_measured:1,metric_boundary:"合成测试",summary:{feedback_rows:6,cases:0,pending_review:0,human_reviewed:0,handoff_ready:true},cases:[]};
  }else throw Error("Unexpected fixture request "+req.method()+" "+pathname);
  await route.fulfill({status:200,contentType:"application/json",body:JSON.stringify(body)});
 });
 return {browser,page,errors,calls,release};
}

test("unified analysis retains input, paused task and edited original comparison across modules",{timeout:60000},async()=>{
 const {browser,page,errors,calls,release}=await setup();
 try{
  await page.goto(base,{waitUntil:"networkidle"});
  assert.equal(await page.getByRole("navigation",{name:"主导航"}).getByRole("button").count(),5);
  await page.getByRole("button",{name:"分析任务",exact:true}).click();
  await page.getByRole("textbox",{name:"素材标题",exact:true}).fill("synthetic/demo 保留输入");
  await page.getByRole("button",{name:"开始分析",exact:true}).click();
  await page.getByText("合成等待人工",{exact:true}).waitFor();
  await page.getByRole("button",{name:"工作台",exact:true}).click();
  await page.getByRole("button",{name:"分析任务",exact:true}).click();
  assert.equal(await page.getByRole("textbox",{name:"素材标题",exact:true}).inputValue(),"synthetic/demo 保留输入");
  assert.equal(await page.getByRole("button",{name:"开始分析",exact:true}).isDisabled(),true);
  await page.getByRole("button",{name:"修改后继续",exact:true}).click();
  const editor=page.getByRole("region",{name:"人工修正表单"});
  await editor.getByRole("textbox",{name:"处理建议",exact:true}).fill("人工确认：优化返回路径，减少连续返回次数");
  await editor.getByRole("textbox",{name:"修改原因或备注",exact:true}).fill("合成核查，保留返回困难标签");
  await page.getByRole("button",{name:"工作台",exact:true}).click();
  await page.getByRole("button",{name:"分析任务",exact:true}).click();
  assert.equal(await editor.getByRole("textbox",{name:"修改原因或备注",exact:true}).inputValue(),"合成核查，保留返回困难标签");
  await editor.getByRole("button",{name:"保存修正并继续",exact:true}).click();
  await page.getByRole("heading",{name:"人工复核结果",exact:true}).waitFor();
  await page.getByText("人工确认：优化返回路径，减少连续返回次数",{exact:true}).waitFor();
  await page.getByText("查看 AI 原始结果（留档）",{exact:true}).click();
  await page.getByText(recommendation.action,{exact:true}).waitFor();
  assert.equal(calls.filter(x=>x.path==="/api/agent/runs").length,1);
  assert.equal(calls.filter(x=>x.path.endsWith("/resume")).length,1);
  assert.deepEqual(errors,[]);
  await mkdir("output/ui-redesign",{recursive:true});
  await page.screenshot({path:"output/ui-redesign/analysis-review-desktop.png",fullPage:true});
 }finally{release();await browser.close();}
});

test("quick analysis and pending business report survive tab and module navigation",{timeout:60000},async()=>{
 const {browser,page,errors,calls,release}=await setup();
 try{
  await page.goto(base,{waitUntil:"networkidle"});
  await page.getByRole("button",{name:"分析任务",exact:true}).click();
  await page.getByRole("radio",{name:/快速分析/}).check();
  await page.getByRole("button",{name:"开始分析",exact:true}).click();
  await page.getByRole("heading",{name:"建议动作",exact:false}).waitFor();
  assert.equal(await page.getByText("原文与判断依据",{exact:true}).isVisible(),false);
  await page.getByText("判断依据与规范来源",{exact:false}).first().click();
  await page.getByText("返回体验演示规范",{exact:false}).waitFor();
  await page.getByRole("button",{name:"交接报告",exact:true}).click();
  const started=page.waitForRequest(r=>new URL(r.url()).pathname==="/api/business/reports");
  await page.getByRole("button",{name:"运行配套模拟案例",exact:true}).click();await started;
  await page.getByRole("button",{name:"工作台",exact:true}).click();
  release();
  await page.getByRole("button",{name:"分析任务",exact:true}).click();
  await page.getByText(/来源：synthetic；本次实测处理耗时 1ms/).waitFor();
  await page.getByRole("button",{name:"新建分析",exact:true}).click();
  await page.getByRole("heading",{name:"建议动作",exact:false}).waitFor();
  assert.equal(calls.filter(x=>x.path==="/api/business/reports").length,1);
  assert.equal(calls.filter(x=>x.path==="/api/analyses"&&x.method==="POST").length,1);
  await page.getByRole("button",{name:"工作台",exact:true}).click();
  await page.getByRole("button",{name:/处理一批反馈/}).click();
  await page.getByRole("heading",{name:"批量反馈分析",exact:true}).waitFor();
  await page.getByRole("button",{name:"工作台",exact:true}).click();
  await page.getByRole("button",{name:"分析任务",exact:true}).click();
  await page.getByRole("heading",{name:"批量反馈分析",exact:true}).waitFor();
  assert.deepEqual(errors,[]);
 }finally{release();await browser.close();}
});

test("review queue opens real correction editor and submits edited recommendations",{timeout:60000},async()=>{
 const {browser,page,errors,calls,release}=await setup();
 try{
  await page.goto(base,{waitUntil:"networkidle"});
  await page.getByRole("button",{name:"人工复核",exact:true}).click();
  await page.getByRole("textbox",{name:"搜索复核记录"}).fill("不匹配");
  await page.getByText("没有符合筛选条件的记录。",{exact:true}).waitFor();
  await page.getByRole("textbox",{name:"搜索复核记录"}).fill("");
  await page.getByRole("button",{name:"查看并复核",exact:true}).click();
  await page.getByRole("button",{name:"编辑修正版",exact:true}).click();
  const editor=page.getByRole("region",{name:"人工修正表单"});
  await editor.getByRole("textbox",{name:"处理建议",exact:true}).fill("人工修订返回建议");
  await editor.getByRole("textbox",{name:"修改原因或备注",exact:true}).fill("synthetic review");
  await editor.getByRole("button",{name:"保存修正并继续",exact:true}).click();
  await page.getByText("人工版本已保存，AI 原始结果保留。",{exact:true}).waitFor();
  const saved=calls.find(x=>x.path.endsWith("/reviews"));
  assert.equal(JSON.parse(saved.body).edited_recommendations[0].action,"人工修订返回建议");
  assert.deepEqual(errors,[]);
  await page.screenshot({path:"output/ui-redesign/review-queue-desktop.png",fullPage:true});
 }finally{release();await browser.close();}
});

test("overview has honest empty state and responsive navigation without page overflow",{timeout:60000},async()=>{
 const {browser,page,errors,release}=await setup();
 try{
  await page.goto(base,{waitUntil:"networkidle"});
  await page.getByText("还没有分析记录",{exact:true}).waitFor();
  await page.screenshot({path:"output/ui-redesign/workspace-desktop.png",fullPage:true});
  await page.setViewportSize({width:390,height:844});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),true);
  await page.screenshot({path:"output/ui-redesign/workspace-mobile.png",fullPage:true});
  await page.getByRole("button",{name:"分析任务",exact:true}).click();
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),true);
  assert.deepEqual(errors,[]);
 }finally{release();await browser.close();}
});
