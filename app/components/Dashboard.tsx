"use client";
/* eslint-disable @typescript-eslint/no-explicit-any, jsx-a11y/label-has-associated-control */
import { useCallback, useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, API } from "../lib/api";
import { BusinessWorkbench } from "./BusinessWorkbench";
import { AgentReviewEditor } from "./AgentReviewEditor";
import { RetainedPage } from "./RetainedPage";
import { EvaluationCenter } from "./EvaluationCenter";
import { WorkspaceChrome, type Screen } from "./WorkspaceChrome";
import { assessmentTitle, resultLabelName } from "../lib/assessment";

type Result={analysis_id:string;labels:{label:string;confidence:number}[];overall_risk:string;confidence:number;evidence:{source:string;quote:string;citation_id?:string}[];citations:{citation_id:string;document_title:string;snippet:string;score:number;source_type?:string;source_url?:string;content_type?:string}[];strategy_recommendations:{category:string;action:string;rationale:string;priority:string;expected_metric:string;guardrail_metric:string}[];requires_human_review:boolean;uncertainties:string[];model_info:{provider:string;model:string;latency_ms:number;input_tokens:number;output_tokens:number;estimated_cost_usd:number|null;simulated:boolean};prompt_version:string;assessment_status?:string;disclaimers?:string[];abstained_labels?:{label:string;confidence:number}[];analysis_policy_version?:string};
const names:Record<string,string>={forced_or_unexpected_jump:"强制/非预期跳转",malicious_or_suspicious_redirect:"恶意/可疑重定向",misleading_claim:"误导宣传",vulgar_or_inappropriate_content:"低俗/不适内容",excessive_ad_frequency:"频率过高",repetitive_material:"素材重复",unclear_material:"素材不清晰",stale_material:"素材陈旧",weak_first_three_seconds:"前三秒弱",irrelevant_targeting:"相关性弱",return_path_friction:"返回路径过长",potential_privacy_risk:"潜在隐私风险",no_issue:"未发现明确问题"};
const initial={title:"合成演示：游戏福利素材",ad_copy:"限时福利，点击查看活动详情",feedback:"点击后自动跳转到陌生页面，进入后连续返回很多次还是回不去",industry:"游戏",media_scene:"锁屏",landing_type:"Deeplink",material_format:"竖版视频",first_three_seconds:"前三秒只有空镜，核心信息出现较晚"};

export function Dashboard(){
 const [page,setPage]=useState<Screen>("项目概览");
 const [lastAnalysis,setLastAnalysis]=useState<Screen>("单条分析");
 const [health,setHealth]=useState<any>();
 const [healthError,setHealthError]=useState("");
 useEffect(()=>{api("/health").then(setHealth).catch(()=>setHealthError("无法连接后端，请确认本地服务已启动。"))},[]);
 const navigate=(screen:Screen)=>{setPage(screen);if(["单条分析","批量分析","综合归因","业务闭环"].includes(screen))setLastAnalysis(screen)};
 return <WorkspaceChrome page={page} lastAnalysis={lastAnalysis} onNavigate={navigate} health={health} healthError={healthError}>
  <RetainedPage active={page==="项目概览"}><Overview go={navigate}/></RetainedPage>
  <RetainedPage active={page==="单条分析"}><Single/></RetainedPage>
  <RetainedPage active={page==="批量分析"}><Batch/></RetainedPage>
  <RetainedPage active={page==="综合归因"}><Comprehensive/></RetainedPage>
  <RetainedPage active={page==="业务闭环"}><BusinessWorkbench/></RetainedPage>
  <RetainedPage active={page==="人工复核"}><Review/></RetainedPage>
  <RetainedPage active={page==="评测中心"}><Evaluation/></RetainedPage>
  <RetainedPage active={page==="Prompt 与规则"}><Policy/></RetainedPage>
  <RetainedPage active={page==="项目复盘"}><CaseStudy/></RetainedPage>
 </WorkspaceChrome>
}

function Overview({go}:{go:(screen:Screen)=>void}){
 const [data,setData]=useState<any>();const [error,setError]=useState("");const [loading,setLoading]=useState(true);
 const load=useCallback(()=>{setLoading(true);setError("");api<any>("/overview").then(setData).catch(e=>setError(e.message)).finally(()=>setLoading(false))},[]);
 useEffect(()=>{api<any>("/overview").then(setData).catch(e=>setError(e.message)).finally(()=>setLoading(false));},[]);
 const riskNames:Record<string,string>={low:"低风险",medium:"中风险",high:"高风险",critical:"极高风险"};
 const chart=Object.entries(data?.risk_distribution||{}).map(([name,value])=>({name:riskNames[name]||name,value}));
 const total=Number(data?.today_analyses||0);
 return <>
  <div className="hero"><div><div className="eyebrow">OVERVIEW</div><h3>让每一条反馈，都有清晰的处理路径</h3><p>从问题识别到证据核对，再到人工确认。在一个工作空间完成广告体验分析。</p></div><button className="primary" onClick={()=>go("单条分析")}>＋ 新建分析</button></div>
  {error&&<div className="error" role="alert">数据暂不可用：{error} <button className="text-button" onClick={load}>重新加载</button></div>}
  <div className="grid four">{[
   ["累计分析记录",data?String(total):"—","当前本地数据库，非今日增量"],
   ["高风险记录",data?String((data.risk_distribution?.high||0)+(data.risk_distribution?.critical||0)):"—","高 / 极高风险原始分析"],
   ["平均分析耗时",data?`${data.average_latency_ms} ms`:"—","记录中的耗时；规则模式包含模拟值"],
   ["风险类别",data?String(Object.values(data.risk_distribution||{}).filter(x=>Number(x)>0).length):"—","当前有记录的风险等级数"],
  ].map(([label,value,note])=><div className="card metric-card" key={label}><div className="metric-label">{label}</div><div className="metric-value">{loading?"…":value}</div><div className="metric-sub">{note}</div></div>)}</div>
  <div className="workspace-overview-grid">
   <div className="card"><div className="section-heading"><div><h4>从这里开始</h4><p className="muted">按你要完成的任务选择入口</p></div><span className="subtle-badge">3 个常用场景</span></div>
    <div className="quick-links">{[
     {screen:"单条分析" as Screen,title:"分析一条反馈",description:"输入素材与反馈，查看结论并完成必要复核。",number:"01"},
     {screen:"批量分析" as Screen,title:"处理一批反馈",description:"上传 CSV，逐条检查；也可切换到按广告汇总。",number:"02"},
     {screen:"人工复核" as Screen,title:"核对高风险结论",description:"查原文、看依据，保存人工修正版。",number:"03"},
    ].map(item=><button type="button" className="quick-link" key={item.number} onClick={()=>go(item.screen)}><span className="quick-number">{item.number}</span><span><strong>{item.title}</strong><small>{item.description}</small></span><span aria-hidden="true">↗</span></button>)}</div>
   </div>
   <div className="card"><div className="section-heading"><div><h4>风险分布</h4><p className="muted">本地已保存的原始分析记录</p></div><button className="text-button" onClick={load} disabled={loading}>刷新</button></div>
    {loading?<div className="state">正在读取记录…</div>:total?<div className="risk-chart" style={{height:230}}><ResponsiveContainer><BarChart data={chart}><CartesianGrid strokeDasharray="3 3" vertical={false}/><XAxis dataKey="name" tickLine={false} axisLine={false}/><YAxis allowDecimals={false} tickLine={false} axisLine={false}/><Tooltip/><Bar dataKey="value" name="分析记录" radius={[5,5,0,0]}>{chart.map((_,i)=><Cell key={i} fill={["#8aaf9e","#d0b56d","#d49477","#b87983"][i]}/>)}</Bar></BarChart></ResponsiveContainer></div>:<div className="state"><strong>还没有分析记录</strong><p>完成一次分析后，这里会显示真实的本地统计。</p></div>}
   </div>
  </div>
  <div className="workflow-strip"><div><span className="eyebrow">处理路径</span><strong>识别问题，保留依据，让人作最终确认</strong></div><ol><li>输入反馈</li><li>检索与分析</li><li>核对证据</li><li>人工确认</li></ol></div>
  <details className="disclosure"><summary>能力范围与数据口径</summary><p className="muted">本工具提供分析和建议，不自动投放、处罚或修改线上配置。以上统计来自本地记录，不代表线上业务效果。人工复核率暂不展示，以免把重复复核记录数误作已复核样本数。图片语义审核以环境配置为准。</p></details>
 </>;
}

function Single(){
 const [form,setForm]=useState(initial);const [image,setImage]=useState<File>();const [fileKey,setFileKey]=useState(0);
 const [mode,setMode]=useState("review");const [result,setResult]=useState<Result>();const [run,setRun]=useState<any>();
 const [loading,setLoading]=useState(false);const [error,setError]=useState("");const [editing,setEditing]=useState(false);
 const update=(k:string,v:string)=>setForm({...form,[k]:v});
 const waiting=run?.status==="awaiting_review";
 async function submit(e:React.FormEvent){
  e.preventDefault();setLoading(true);setError("");
  try{
   if(mode==="review"){
    const next:any=await api("/agent/runs",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(form)});setRun(next);setResult(undefined);setEditing(false);
   }else{
    let output:Result;
    if(image){const body=new FormData();body.append("payload",JSON.stringify(form));body.append("file",image);output=await api<Result>("/analyses/image",{method:"POST",body})}
    else output=await api<Result>("/analyses",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(form)});
    setResult(output);setRun(undefined);
   }
  }catch(e:any){setError(e.message)}finally{setLoading(false)}
 }
 async function resume(decision:"accepted"|"modified",corrections:Record<string,unknown>={}){
  setLoading(true);setError("");try{setRun(await api(`/agent/runs/${run.thread_id}/resume`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({decision,notes:"人工确认分析结论",...corrections})}));setEditing(false)}catch(e:any){setError(e.message)}finally{setLoading(false)}
 }
 const effective=run?.corrected_output||run?.output||result;
 const reset=()=>{setForm(initial);setImage(undefined);setFileKey(x=>x+1)};
 return <>
  <div className="hero"><div><h3>新建反馈分析</h3><p>填写反馈，查看问题线索与处理建议。默认在需要时暂停，等待人工确认。</p></div><span className="subtle-badge">单条分析</span></div>
  <div className="analysis-layout"><form className="card input-card" onSubmit={submit}><div className="section-heading"><h4>素材与用户反馈</h4><span className="muted">合成样例，可自行修改</span></div>
   <fieldset className="mode-picker" disabled={loading||waiting}><legend>处理方式</legend><label><input type="radio" name="analysis-mode" value="review" checked={mode==="review"} onChange={()=>setMode("review")}/> 分析并人工确认 <small>高风险自动暂停</small></label><label><input type="radio" name="analysis-mode" value="quick" checked={mode==="quick"} onChange={()=>setMode("quick")}/> 快速分析 <small>支持关联图片</small></label></fieldset>
   <fieldset className="input-fields" disabled={loading||waiting}><div className="form-grid">
    <Field full label="素材标题" value={form.title} set={v=>update("title",v)}/>
    <Field area full label="用户反馈文本" value={form.feedback} set={v=>update("feedback",v)}/>
    <Field area full label="广告文案" value={form.ad_copy} set={v=>update("ad_copy",v)}/>
    <Select label="行业" value={form.industry} set={v=>update("industry",v)} options={["游戏","电商","金融","工具","内容","教育","医疗","其他"]}/>
    <Select label="媒体场景" value={form.media_scene} set={v=>update("media_scene",v)} options={["锁屏","负一屏/智慧桌面","天气","浏览器","视频","其他"]}/>
    <Select label="落地类型" value={form.landing_type} set={v=>update("landing_type",v)} options={["Web","浏览器详情页","Deeplink","应用下载","快应用","其他"]}/>
    <Select label="素材形式" value={form.material_format} set={v=>update("material_format",v)} options={["图片","横版视频","竖版视频","图文"]}/>
   </div><details className="optional-inputs"><summary>补充素材信息（可选）</summary><Field area full label="视频前 3 秒描述" value={form.first_three_seconds} set={v=>update("first_three_seconds",v)}/>
    {mode==="quick"?<label className="field">图片上传<input key={fileKey} type="file" accept="image/png,image/jpeg,image/webp" onChange={e=>setImage(e.target.files?.[0])}/><small className="muted">PNG/JPEG/WebP，最大 5MB；仅在后端启用视觉审核时分析图片内容。</small></label>:<p className="muted">需要关联图片时，请选择快速分析；人工确认流程当前分析文字信息。</p>}
   </details></fieldset>
   {error&&<div className="error" role="alert">{error}</div>}
   {waiting&&<p className="review-notice">当前任务等待人工确认。完成右侧复核后，可发起下一次分析。</p>}
   <div className="actions"><button className="primary" disabled={loading||waiting}>{loading?"正在分析…":"开始分析"}</button><button type="button" className="secondary" disabled={loading||waiting} onClick={reset}>恢复样例</button></div>
  </form>
  <div className="analysis-output" aria-live="polite">
   {!effective?<div className="card analysis-empty"><div className="empty-mark" aria-hidden="true">↗</div><h4>{loading?"正在检索与分析":"分析结果将在这里呈现"}</h4><p>{loading?"请稍候，切换模块不会中断当前页面请求。":"先看结论与建议，需要时再展开原文证据和执行过程。"}</p><div className="empty-steps"><span>问题标签</span><span>可追溯依据</span><span>人工复核</span></div></div>:<>
    {waiting&&<div className="review-notice"><strong>等待人工确认</strong><p>{run.interrupt?.reason}</p><div className="actions"><button type="button" className="primary" disabled={loading} onClick={()=>resume("accepted")}>接受并继续</button><button type="button" className="secondary" disabled={loading} onClick={()=>setEditing(true)}>修改后继续</button></div></div>}
    {editing&&waiting&&<AgentReviewEditor output={run.output} names={names} busy={loading} onSave={payload=>resume("modified",payload)} onCancel={()=>setEditing(false)}/>}
    {run?.corrected_output&&<div className="success">人工复核记录已保存，原始分析保留。</div>}
    <ResultPanel result={effective} human={!!run?.corrected_output}/>
    {run?.human_decision?.notes&&<p className="evidence">人工备注：{run.human_decision.notes}</p>}
    {run?.corrected_output&&<details className="disclosure"><summary>查看 AI 原始结果（留档）</summary><ResultPanel result={run.output}/></details>}
    {run&&<details className="disclosure"><summary>执行过程 · {waiting?"等待人工":"已完成"}</summary><p className="muted">任务 {run.thread_id?.slice(0,8)} · {run.status}。暂停状态保存在服务内存，重启后不可恢复；已保存记录保留。</p><div className="agent-trace">{run.trace.map((x:any,i:number)=><div className="agent-step" key={`${x.node}-${i}`}><b>{i+1}. {({validate_input:"检查输入",retrieve_policy:"检索规范",analyze_risk:"分析风险",human_review:"人工复核",finalize:"完成任务"} as Record<string,string>)[x.node]||x.node}</b><span>{x.detail}</span></div>)}</div></details>}
   </>}
  </div></div>
 </>;
}

function Field({label,value,set,area,full}:{label:string,value:string,set:(v:string)=>void,area?:boolean,full?:boolean}){return <div className={`field ${full?"full":""}`}><label>{label}</label>{area?<textarea aria-label={label} value={value} onChange={e=>set(e.target.value)}/>:<input aria-label={label} value={value} onChange={e=>set(e.target.value)}/>}</div>}
function Select({label,value,set,options}:{label:string,value:string,set:(v:string)=>void,options:string[]}){return <div className="field"><label>{label}</label><select aria-label={label} value={value} onChange={e=>set(e.target.value)}>{options.map(x=><option key={x}>{x}</option>)}</select></div>}
function ResultPanel({result,human=false}:{result:Result;human?:boolean}) {
 const riskNames:Record<string,string>={low:"低风险",medium:"中风险",high:"高风险",critical:"极高风险"};
 const categories:Record<string,string>={product:"产品策略",creative:"素材优化",delivery:"投放建议",review:"人工核查"};
 const sources:Record<string,string>={synthetic_demo:"合成演示规范",internal_simulated:"个人模拟规则",official_regulation_summary:"公开法规摘要",official_platform_summary:"公开平台规则摘要",public:"公开资料"};
 return <div className="card result-card">
  <div className="section-heading"><div><span className="eyebrow">{human?"人工确认":"分析结论"}</span><h4>{human?"人工复核结果":assessmentTitle(result.assessment_status)}</h4></div><span className={`risk ${result.overall_risk}`}>{riskNames[result.overall_risk]||result.overall_risk}</span></div>
  <div className="labels">{result.labels.map(x=><span className="label" key={x.label}>{resultLabelName(x.label,result.assessment_status,names)} <small>· {human?"人工选择":`${Math.round(x.confidence*100)}%`}</small></span>)}</div>
  {result.assessment_status==="insufficient_evidence"&&<p className="review-notice">当前信息不足，暂不分类不代表已核验正常。</p>}
  {human?<p className="muted">复核已完成；未自动执行投放处置或正式放行。</p>:result.requires_human_review&&<p className="review-notice compact">需要人工核查 · 当前结论是待验证线索。</p>}
  <div className="result-section"><h4>建议动作 <span className="count-label">{result.strategy_recommendations.length}</span></h4>{result.strategy_recommendations.length?result.strategy_recommendations.map((r,i)=><div className="recommendation" key={i}><div className="recommendation-meta"><span className={`priority priority-${r.priority.toLowerCase()}`}>{r.priority}</span><span>{categories[r.category]||r.category}</span></div><strong>{r.action}</strong><p>{r.rationale}</p><details className="metric-details"><summary>目标与护栏</summary><p>目标：{r.expected_metric}</p><p>护栏：{r.guardrail_metric}</p></details></div>):<p className="muted">暂无建议，请结合原文人工判断。</p>}</div>
  {!!result.uncertainties.length&&<div className="uncertainty-box"><h4>还需要确认</h4><ul>{result.uncertainties.map(x=><li key={x}>{x}</li>)}</ul></div>}
  <details className="disclosure"><summary>判断依据与规范来源 <span className="count-label">{result.evidence.length} 条依据 · {result.citations.length} 个片段</span></summary>
   <h4>{human?"原始分析证据（留档，未随人工标签重新核验）":"原文与判断依据"}</h4>
   {result.evidence.length?result.evidence.map((e,i)=><div className="evidence" key={i}><small>{e.source==="input"?"用户输入":e.source==="retrieval"?"规范引用":"素材信息"}{e.citation_id&&` · ${e.citation_id}`}</small><p>“{e.quote}”</p></div>):<p className="muted">暂无可引用的原文依据。</p>}
   <h4>检索到的规范片段</h4>{result.citations.length?result.citations.map(c=><div className="evidence" key={c.citation_id}><b>{c.citation_id} · {c.document_title}</b><p>{c.snippet}</p><small>{sources[c.source_type||""]||c.source_type} · 检索相关分数 {c.score}（不是置信度）</small>{c.source_url&&<p><a href={c.source_url} target="_blank" rel="noreferrer">查看发布方原文 ↗</a></p>}</div>):<p className="muted">没有匹配证据，不生成虚假引用。</p>}
  </details>
  <details className="disclosure"><summary>运行详情与范围说明</summary><dl className="runtime-facts"><div><dt>模型</dt><dd>{result.model_info.model}</dd></div><div><dt>提示词版本</dt><dd>{result.prompt_version}</dd></div><div><dt>耗时</dt><dd>{result.model_info.latency_ms} ms{result.model_info.simulated?"（模拟）":""}</dd></div><div><dt>用量</dt><dd>{result.model_info.input_tokens+result.model_info.output_tokens} Tokens{result.model_info.simulated?"（模拟）":""}</dd></div><div><dt>费用</dt><dd>{result.model_info.estimated_cost_usd===null?"未知":`$${result.model_info.estimated_cost_usd.toFixed(4)}${result.model_info.simulated?"（模拟）":""}`}</dd></div><div><dt>策略版本</dt><dd>{result.analysis_policy_version||"legacy-v1"}</dd></div></dl>
   {!!result.abstained_labels?.length&&<p className="muted">未采纳的候选：{result.abstained_labels.map(x=>names[x.label]||x.label).join("、")}。具体证据不足或与证据状态冲突。</p>}
   {result.disclaimers?.map(x=><p className="muted" key={x}>{x}</p>)}
  </details>
 </div>;
}

function Batch(){const [file,setFile]=useState<File>();const [result,setResult]=useState<any>();const [loading,setLoading]=useState(false);const [error,setError]=useState("");async function upload(){if(!file)return;setLoading(true);setError("");const body=new FormData();body.append("file",file);try{setResult(await api("/batch",{method:"POST",body}))}catch(e:any){setError(e.message)}finally{setLoading(false)}}return <><div className="hero"><div><h3>批量反馈分析</h3><p>白名单校验、逐行错误提示和敏感字段拦截。文件上限 2MB，仅支持 UTF-8 CSV。</p></div><a className="secondary" href={`${API}/batch/template`}>下载模板</a></div><div className="card"><div className="upload"><input type="file" accept=".csv,text/csv" onChange={e=>setFile(e.target.files?.[0])}/><p className="muted">禁止 IMEI、手机号、姓名、身份证、邮箱与设备标识字段。</p><button className="primary" disabled={!file||loading} onClick={upload}>{loading?"逐行分析中…":"上传并执行"}</button></div>{error&&<div className="error">{error}</div>}{result&&<div className="success">完成 {result.processed} 条，失败 {result.failed} 条。</div>}</div>{result?.results?.length>0&&<div className="card" style={{marginTop:16}}><div className="table-wrap"><table><thead><tr><th>分析 ID</th><th>标签</th><th>风险</th><th>人工复核</th><th>耗时</th></tr></thead><tbody>{result.results.map((x:Result)=><tr key={x.analysis_id}><td>{x.analysis_id.slice(0,8)}</td><td>{x.labels.map(l=>resultLabelName(l.label,x.assessment_status,names)).join("、")}</td><td><span className={`risk ${x.overall_risk}`}>{x.overall_risk}</span></td><td>{x.requires_human_review?"是":"否"}</td><td>{x.model_info.latency_ms} ms</td></tr>)}</tbody></table></div></div>}</>}

function Comprehensive(){
 const [table,setTable]=useState<File>();const [images,setImages]=useState<File[]>([]);const [result,setResult]=useState<any>();const [loading,setLoading]=useState(false);const [error,setError]=useState("");
 async function run(){if(!table)return;setLoading(true);setError("");const body=new FormData();body.append("table",table);images.forEach(file=>body.append("images",file));try{setResult(await api("/comprehensive",{method:"POST",body}))}catch(e:any){setError(e.message)}finally{setLoading(false)}}
 return <><div className="hero"><div><h3>广告负反馈综合归因</h3><p>上传反馈表与素材图片，按广告 ID 聚合多条反馈，定位主要原因、风险等级、证据、素材质量与人工复核优先级。</p></div><a className="secondary" href={`${API}/comprehensive/template`}>下载综合分析模板</a></div>
 <div className="card"><div className="form-grid"><div className="field"><label>负反馈表（CSV）</label><input type="file" accept=".csv,text/csv" onChange={e=>setTable(e.target.files?.[0])}/><span className="muted">必填字段：ad_id、feedback；可选 image_filename、广告文案和场景信息。</span></div><div className="field"><label>广告素材图片（可多选）</label><input type="file" multiple accept="image/png,image/jpeg,image/webp" onChange={e=>setImages(Array.from(e.target.files||[]))}/><span className="muted">文件名需与 CSV 中 image_filename 一致；每张最大 5MB。</span></div></div><div className="actions"><button className="primary" disabled={!table||loading} onClick={run}>{loading?"正在逐条分析并聚合…":"运行综合分析"}</button><span className="muted">已选择 {images.length} 张图片</span></div>{error&&<div className="error">{error}</div>}{result&&<div className="success">已分析 {result.processed} 条反馈、{result.summary.total_ads} 个广告；失败 {result.failed} 条。</div>}</div>
 {result&&<><div className="grid four" style={{marginTop:16}}>{[["反馈记录",result.summary.total_rows,"CSV 总行数"],["广告数量",result.summary.total_ads,"按 ad_id 聚合"],["匹配素材",`${result.summary.matched_images}/${result.summary.uploaded_images}`,"已关联 / 已上传"],["待人工复核",result.summary.review_required_ads,"高风险、缺图或视觉未确认"]].map(x=><div className="card" key={String(x[0])}><div className="metric-label">{x[0]}</div><div className="metric-value">{x[1]}</div><div className="metric-sub">{x[2]}</div></div>)}</div>
 <div className="grid two" style={{marginTop:16}}><div className="card"><h4>全表原因分布</h4>{result.cause_distribution.length?<div className="table-wrap"><table><thead><tr><th>原因</th><th>出现次数</th><th>涉及广告</th><th>反馈占比</th></tr></thead><tbody>{result.cause_distribution.map((x:any)=><tr key={x.label}><td>{x.name}</td><td>{x.occurrences}</td><td>{x.affected_ads}</td><td>{Math.round(x.feedback_share*100)}%</td></tr>)}</tbody></table></div>:<div className="state">未发现明确风险原因。</div>}</div><div className="card"><h4>风险分布与能力边界</h4><div className="pill-row">{Object.entries(result.summary.risk_distribution).map(([risk,count])=><span className={`risk ${risk}`} key={risk}>{risk.toUpperCase()} · {String(count)}</span>)}</div>{result.limitations.map((x:string)=><p className="muted" key={x}>• {x}</p>)}</div></div>
 <div className="card" style={{marginTop:16}}><h4>按广告 ID 的综合原因</h4>{result.ads.map((ad:any)=><div className="ad-analysis" key={ad.ad_id}><div className="ad-analysis-head"><div><strong>{ad.ad_id}</strong><p>{ad.summary}</p></div><span className={`risk ${ad.overall_risk}`}>{ad.overall_risk.toUpperCase()}</span></div><div className="labels">{ad.dominant_causes.map((x:any)=><span className="label" key={x.label}>{x.name} · {x.count}次</span>)}{ad.requires_human_review&&<span className="label">需要人工复核</span>}</div>{ad.evidence_samples.length>0&&<p className="muted">反馈证据：{ad.evidence_samples.join("；")}</p>}{ad.images.map((img:any)=><p className="muted" key={img.filename}>素材：{img.filename} · {img.width&&img.height?`${img.width}×${img.height}`:"尺寸未知"}{img.basic_findings.length?` · ${img.basic_findings.join("；")}`:" · 基础尺寸检查正常"} · 图片语义{img.semantic_review==="provider"?"已交由视觉模型":"未识别"}</p>)}{ad.missing_images.length>0&&<div className="error">未匹配素材：{ad.missing_images.join("、")}</div>}{ad.recommendations.length>0&&<p className="muted">建议：{ad.recommendations.slice(0,3).join("；")}</p>}</div>)}</div></>}
 </>
}

function Review(){
 const [rows,setRows]=useState<any[]>([]);const [message,setMessage]=useState("");const [error,setError]=useState("");const [loading,setLoading]=useState(true);
 const [query,setQuery]=useState("");const [risk,setRisk]=useState("all");const [selected,setSelected]=useState<any>();const [editing,setEditing]=useState(false);const [busy,setBusy]=useState(false);const [saved,setSaved]=useState<any>();
 const load=useCallback(()=>{setLoading(true);setError("");return api<any[]>("/analyses?review_required=true").then(setRows).catch(e=>setError(e.message)).finally(()=>setLoading(false))},[]);
 useEffect(()=>{api<any[]>("/analyses?review_required=true").then(setRows).catch(e=>setError(e.message)).finally(()=>setLoading(false));},[]);
 async function decide(decision:"accepted"|"modified",corrections:Record<string,unknown>={}){
  if(!selected)return;setBusy(true);setError("");try{const response:any=await api(`/analyses/${selected.id}/reviews`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({decision,reviewer:"demo_reviewer",notes:"人工确认原始分析",...corrections})});setSaved(response.corrected);setEditing(false);setMessage("人工版本已保存，AI 原始结果保留。")}catch(e:any){setError(e.message)}finally{setBusy(false)}
 }
 const filtered=rows.filter(row=>(risk==="all"||row.output.overall_risk===risk)&&`${row.input.feedback} ${row.input.title} ${row.id}`.toLowerCase().includes(query.toLowerCase()));
 return <>
  <div className="hero"><div><h3>人工复核队列</h3><p>先选样本，再查看依据与修正结论。分析标记需复核的记录保留在这里，包含历史已处理样本。</p></div><button className="secondary" disabled={loading} onClick={load}>刷新记录</button></div>
  {message&&<div className="success" role="status">{message}</div>}{error&&<div className="error" role="alert">{error}</div>}
  <div className="review-workspace"><div className="card review-list"><div className="section-heading"><h4>需复核记录</h4><span className="count-label">最近 {rows.length} 条以内</span></div><div className="table-toolbar"><input aria-label="搜索复核记录" placeholder="搜索反馈、标题或编号" value={query} onChange={e=>setQuery(e.target.value)}/><select aria-label="筛选风险等级" value={risk} onChange={e=>setRisk(e.target.value)}><option value="all">全部风险</option><option value="critical">极高风险</option><option value="high">高风险</option><option value="medium">中风险</option><option value="low">低风险</option></select></div>
   {loading?<div className="state">正在加载复核记录…</div>:!filtered.length?<div className="state">{rows.length?"没有符合筛选条件的记录。":"暂无需复核记录，可先完成一次快速分析。"}</div>:<div className="table-wrap"><table><thead><tr><th>反馈与标签</th><th>风险</th><th>操作</th></tr></thead><tbody>{filtered.map(row=><tr key={row.id} className={selected?.id===row.id?"selected-row":""}><td><strong className="feedback-excerpt">{row.input.feedback}</strong><p className="muted">{row.output.labels.map((x:any)=>resultLabelName(x.label,row.output.assessment_status,names)).join(" · ")}</p><small className="muted">{row.id.slice(0,8)}</small></td><td><span className={`risk ${row.output.overall_risk}`}>{({low:"低",medium:"中",high:"高",critical:"极高"} as Record<string,string>)[row.output.overall_risk]}</span></td><td><button className="text-button" onClick={()=>{setSelected(row);setSaved(undefined);setEditing(false);setMessage("");setError("")}}>查看并复核</button></td></tr>)}</tbody></table></div>}
   <p className="muted">列表接口返回最近 200 条以内，按原始需复核标记筛选；暂不提供跨会话的已处理状态筛选。</p>
  </div><div className="review-detail">{selected?<>
   <div className="card"><div className="section-heading"><h4>样本详情</h4><span className="subtle-badge">{selected.id.slice(0,8)}</span></div><blockquote>{selected.input.feedback}</blockquote><p className="muted">{selected.input.title} · {selected.input.media_scene}</p>{!saved&&<div className="actions"><button className="primary" disabled={busy} onClick={()=>decide("accepted")}>接受原结论</button><button className="secondary" disabled={busy} onClick={()=>setEditing(true)}>编辑修正版</button></div>}</div>
   {editing&&<AgentReviewEditor key={selected.id} output={selected.output} names={names} busy={busy} onSave={payload=>decide("modified",payload)} onCancel={()=>setEditing(false)}/>}
   <ResultPanel result={saved||selected.output} human={!!saved}/>
   {saved&&<details className="disclosure"><summary>查看 AI 原始结果</summary><ResultPanel result={selected.output}/></details>}
  </>:<div className="card analysis-empty"><div className="empty-mark" aria-hidden="true">✓</div><h4>选择一条记录开始复核</h4><p>在这里集中查看结论、原文与规范，保存独立的人工版本。</p></div>}</div></div>
 </>;
}

function Evaluation(){return <EvaluationCenter/>}

function Policy(){const [prompts,setPrompts]=useState<any[]>([]);const [name,setName]=useState("候选 Prompt");const [content,setContent]=useState("严格依据输入和 citation_ids 输出多标签结论；证据不足时写入 uncertainties；不得自动处罚或编造引用。");const [message,setMessage]=useState("");const load=useCallback(()=>api<any[]>("/prompts").then(setPrompts).catch(()=>{}),[]);useEffect(()=>{void load();},[load]);async function create(){await api("/prompts",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({name,content})});setMessage("新版本已创建，历史版本保持只读。");load()}async function activate(v:string){await api(`/prompts/${v}/activate`,{method:"POST"});setMessage(`已回滚/切换到 ${v}`);load()}return <><div className="hero"><div><h3>知识库与配置</h3><p>密钥仅由后端环境读取；前端只展示安全的 Prompt 内容和版本元数据。</p></div></div>{message&&<div className="success">{message}</div>}<div className="grid two"><div className="card"><h4>Prompt 版本</h4>{prompts.map(p=><div className="review-item" key={p.version}><div><b>{p.name}</b> {p.is_active&&<span className="badge">当前</span>}<p className="muted">{p.version} · {p.content}</p></div>{!p.is_active&&<button className="secondary" onClick={()=>activate(p.version)}>回滚到此版</button>}</div>)}</div><div className="card"><h4>新建候选版本</h4><div className="field"><label>名称</label><input value={name} onChange={e=>setName(e.target.value)}/></div><div className="field" style={{marginTop:12}}><label>Prompt 内容</label><textarea value={content} onChange={e=>setContent(e.target.value)} /></div><button className="primary" style={{marginTop:14}} onClick={create}>保存只读版本</button></div></div><div className="card" style={{marginTop:16}}><h4>规则资产</h4><div className="pill-row">{Object.values(names).map(x=><span className="label" key={x}>{x}</span>)}</div><p className="muted">知识库包含：跳转与返回、低俗与恶意内容、频控与重复素材、清晰度与新鲜度、视频前三秒、隐私权限、人工复核与风险升级。包含明确标记的合成演示规范与公开规则摘要；公开摘要不等于官方原文。</p><details className="disclosure"><summary>实验设计 · 稳定匿名分桶</summary><Experiment/></details></div></>}
function Experiment(){const [id,setId]=useState("anonymous-demo-user-001");const [result,setResult]=useState<any>();return <div style={{marginTop:24}}><h4>Experiment Design · 稳定匿名分桶</h4><div className="actions"><input style={{padding:9,border:"1px solid #d5dce5",borderRadius:8,minWidth:280}} value={id} onChange={e=>setId(e.target.value)}/><button className="secondary" onClick={async()=>setResult(await api("/experiment/assign",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({anonymous_user_id:id})}))}>计算分组</button></div>{result&&<p className="success">桶 {result.bucket} → {result.group}。相同匿名 ID 稳定进入同组，salt 不返回前端。</p>}<p className="muted">0–59 主实验组、60–69 小实验组、70–99 对照组。灰度发布不等于 A/B 测试；因果评估仍需随机分流、主指标、护栏指标、样本量与实验周期。</p></div>}

function CaseStudy(){return <><div className="hero"><div><h3>个人作品复盘</h3><p>基于公开规则、完全合成数据和用户自行输入构建；不接入 vivo 内部系统，不使用内部数据，也不声称带来真实 CTR 或收入提升。</p></div></div><div className="grid two"><div className="card"><section className="case-section"><h4>背景与用户</h4><p>广告商业化产品经理、体验治理、内容审核和运营人员需要从大量非结构化反馈中快速形成一致、可追溯的判断。</p></section><section className="case-section"><h4>问题与方案</h4><p>标签不统一、依据难追溯、策略难闭环。方案把输入校验、敏感信息拦截、规则预判、本地检索、结构化生成、后处理、复核和评测串成一条链路。</p></section><section className="case-section"><h4>指标设计</h4><p>效果看高风险 recall、Macro/Micro F1 和建议人评；效率看平均耗时与人工复核率；成本看单次估算；护栏看误报、误拦截和可投覆盖率。</p></section></div><div className="card"><section className="case-section"><h4>3 分钟讲解提纲</h4><ol><li>30 秒：真实业务观察与作品事实边界。</li><li>60 秒：从反馈到证据、建议和复核闭环。</li><li>50 秒：为什么 Demo Mode、结构化 schema 与规则后处理重要。</li><li>30 秒：用固定合成集评测，高风险优先关注召回率。</li><li>10 秒：下一步是视觉模型、向量检索与真实匿名人评。</li></ol></section><section className="case-section"><h4>失败案例与风险</h4><p>覆盖检索正确但生成错误、错误召回、多标签漏检、模糊反馈过推断，以及规则与模型冲突。系统保留不确定性、追溯引用和人工修正版。</p></section><section className="case-section"><h4>事实边界</h4><p>可以说“我基于过往广告体验治理观察做了独立作品”；不能说“接入 vivo 系统、使用内部 2,149 条数据、已经上线或提升 CTR”。</p></section></div></div></>}
