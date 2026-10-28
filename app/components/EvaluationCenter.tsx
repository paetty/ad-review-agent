"use client";
/* eslint-disable @typescript-eslint/no-explicit-any */
import { useEffect, useState } from "react";
import { api } from "../lib/api";

const names:Record<string,string>={forced_or_unexpected_jump:"非预期跳转",malicious_or_suspicious_redirect:"可疑网站/重定向",misleading_claim:"误导宣传",vulgar_or_inappropriate_content:"不适内容",excessive_ad_frequency:"频率过高",repetitive_material:"素材重复",unclear_material:"素材不清晰",stale_material:"素材陈旧/过期",weak_first_three_seconds:"前三秒问题",irrelevant_targeting:"相关性弱",return_path_friction:"返回困难",potential_privacy_risk:"隐私风险",no_issue:"no_issue占位/未见问题"};
const textLabels=(xs:string[])=>xs.map(x=>names[x]||x).join("、");
const states:Record<string,string>={queued:"排队中",running:"运行中",completed:"完成",partial:"完成但有调用失败",failed:"执行失败",interrupted:"服务重启已中断"};
const assessments:Record<string,string>={issue_detected:"发现问题线索",insufficient_evidence:"证据不足",no_explicit_issue:"未见明确问题"};
const percent=(n:number|null|undefined)=>n==null?"不适用":`${(n*100).toFixed(1)}%`;

export function EvaluationCenter(){
 const [catalog,setCatalog]=useState<any[]>([]),[dataset,setDataset]=useState("development"),[mode,setMode]=useState("rules");
 const [preview,setPreview]=useState<any>(),[confirmed,setConfirmed]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState("");
 const [runId,setRunId]=useState<number>(),[run,setRun]=useState<any>(),[history,setHistory]=useState<any[]>([]),[onlyErrors,setOnlyErrors]=useState(false);
 useEffect(()=>{api<any>("/evaluations/datasets").then(x=>setCatalog(x.datasets)).catch(e=>setError(e.message));api<any[]>("/evaluations/runs").then(setHistory).catch(e=>setError(e.message))},[]);
 useEffect(()=>{
  if(runId===undefined)return;
  let disposed=false;let timer:ReturnType<typeof setTimeout>;
  async function poll(){
   try{const value=await api<any>(`/evaluations/runs/${runId}`);if(disposed)return;setRun(value);
    if(["queued","running"].includes(value.status)){timer=setTimeout(poll,1200)}else{api<any[]>("/evaluations/runs").then(x=>{if(!disposed)setHistory(x)}).catch(()=>{})}
   }catch(e:any){if(!disposed){setError(e.message);timer=setTimeout(poll,3000)}}
  }
  void poll();return()=>{disposed=true;clearTimeout(timer)};
 },[runId]);
 const running=run&&["queued","running"].includes(run.status);
 const change=()=>{setPreview(undefined);setConfirmed(false);setError("")};
 async function inspect(){setBusy(true);setError("");try{setPreview(await api("/evaluations/preview",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({dataset,mode})}));setConfirmed(false)}catch(e:any){setError(e.message)}finally{setBusy(false)}}
 async function start(){if(!preview)return;setBusy(true);setError("");try{const value=await api<any>("/evaluations/runs",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({dataset,mode,dataset_sha256:preview.dataset.sha256,confirm_provider:confirmed})});setRun({status:"queued",processed:0,total:preview.analyses,items:[]});setRunId(value.run_id)}catch(e:any){setError(e.message)}finally{setBusy(false)}}
 async function openRun(id:number){setBusy(true);setError("");try{setRun(await api(`/evaluations/runs/${id}`));setRunId(id);setOnlyErrors(false)}catch(e:any){setError(e.message)}finally{setBusy(false)}}
 const selected=catalog.find(x=>x.id===dataset);
 const items=(run?.items||[]).filter((x:any)=>!onlyErrors||!x.matched);
 return <>
  <div className="hero"><div><h3>统一评测中心</h3><p>开发集用于发现并修复错误；验证集用于阶段比较。所有当前数据均为合成案例，不是企业独立盲测。</p></div></div>
  <div className="card"><h4>1. 选择题库与运行方式</h4><div className="form-grid">
   <label className="field">评测数据集<select aria-label="评测数据集" value={dataset} disabled={busy||running} onChange={e=>{setDataset(e.target.value);change()}}>{catalog.map(x=><option key={x.id} value={x.id}>{x.name} · {x.count}条</option>)}</select></label>
   <label className="field">运行模式<select aria-label="运行模式" value={mode} disabled={busy||running} onChange={e=>{setMode(e.target.value);change()}}><option value="rules">规则基线（不调用模型）</option><option value="provider">真实模型＋规则＋当前RAG</option></select></label>
  </div><p className="muted">{selected?.description}</p><p className="muted">此处的模式独立于其他分析页面。12条留出候选不开放运行；12条检索查询属于另一种实验，不混入分类评测。</p>
  <button className="secondary" disabled={busy||running||!catalog.length} onClick={inspect}>{busy?"处理中…":"2. 预览条数与调用量"}</button>
  {preview&&<div className="evidence"><b>{preview.dataset.name}：{preview.analyses}条</b><p>预计模型逻辑调用：{preview.expected_model_calls}次；最多HTTP尝试：{preview.maximum_http_attempts}次。</p><p>模型：{preview.model||"未配置"}；{mode==="rules"?"无API费用，Token字段为模拟值。":"实际费用未知，结果中记录服务返回的Token；需要自行核对账单。"}</p><p className="muted">{preview.notice}</p>
   {mode==="provider"&&<label><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/>我确认本次预计{preview.expected_model_calls}次模型调用及可能费用</label>}
   {mode==="provider"&&!preview.provider_configured&&<p className="error">后端模型配置不完整，请先完成配置。</p>}
   <div className="actions"><button className="primary" disabled={busy||running||(mode==="provider"&&(!confirmed||!preview.provider_configured))} onClick={start}>3. 开始本次评测</button></div>
  </div>}
  </div>
  {error&&<div className="error" role="alert">{error}</div>}
  {run&&<div className="card" style={{marginTop:16}}><h4>运行 #{runId} · {states[run.status]||run.status}</h4><p>{run.dataset?.name} · {run.mode==="rules"?"规则基线":"模型链路"} · {run.model} · Prompt {run.prompt_version}</p><p>进度：{run.processed}/{run.total}；调用失败：{run.failed||0}条。切换菜单后仍可回来查看。</p><progress aria-label="评测进度" value={run.processed} max={run.total}/>{run.error&&<p className="error">{run.error}</p>}
   {run.metrics&&<><div className="grid four">{[["标签完全匹配",percent(run.metrics.exact_match_ratio)],["Micro F1",run.metrics.micro_f1],["Macro F1（全部13类）",run.metrics.macro_f1],["高风险Recall",percent(run.metrics.high_risk_recall)]].map(([name,value])=><div className="card" key={name}><div className="metric-label">{name}</div><div className="metric-value">{value}</div></div>)}</div>
    <p>各适用项同时符合参考：{run.metrics.all_checks_match_count}/{run.metrics.records}；状态参考样本：{run.metrics.status_reference_count}；状态匹配：{percent(run.metrics.status_match_ratio)}。</p>
    <p>平均实测分析耗时：{run.metrics.average_measured_pipeline_ms}ms；{run.metrics.tokens_simulated?"模拟":"服务返回"}Token：输入{run.metrics.input_tokens}＋输出{run.metrics.output_tokens}；费用：{run.metrics.estimated_cost_usd===null?"未知":"$0（规则基线）"}。</p>
    <p className="muted">{run.metrics.warning} Macro F1包含本数据集未出现的标签，样本少时不能单独用于判断总体效果。</p>
    <details><summary>查看各标签Precision / Recall / F1 / Support</summary><table><thead><tr><th>标签</th><th>Precision</th><th>Recall</th><th>F1</th><th>Support</th></tr></thead><tbody>{Object.entries(run.metrics.per_label).map(([key,v]:any)=><tr key={key}><td>{names[key]}</td><td>{v.precision}</td><td>{v.recall}</td><td>{v.f1}</td><td>{v.support}</td></tr>)}</tbody></table></details>
   </>}
   <h4>4. 查看逐条参考与实际结果</h4><label><input type="checkbox" checked={onlyErrors} onChange={e=>setOnlyErrors(e.target.checked)}/>只看不符合参考或调用失败</label>
   {!items.length&&<p className="state">{running?"等待条目返回…":onlyErrors?"没有不符合参考的条目。":"暂无逐条结果。"}</p>}
   {items.map((x:any)=><details className="evidence" key={x.record_id}><summary>{x.record_id} · {x.error?"调用失败":x.matched?"符合参考":"存在差异"} · {x.input.feedback}</summary><table><thead><tr><th>检查项</th><th>参考</th><th>实际</th></tr></thead><tbody>
    <tr><td>标签</td><td>{textLabels(x.reference.labels)}</td><td>{x.output?textLabels(x.output.labels.map((l:any)=>l.label)):"无输出"}</td></tr>
    <tr><td>风险</td><td>{x.reference.risk}</td><td>{x.output?.overall_risk||"无输出"}</td></tr>
    <tr><td>证据状态</td><td>{assessments[x.reference.status]||"旧样例未标注，不计此项"}</td><td>{assessments[x.output?.assessment_status]||"无输出"}</td></tr>
    <tr><td>人工复核</td><td>{x.reference.review?"需要":"不强制"}</td><td>{x.output?(x.output.requires_human_review?"需要":"不强制"):"无输出"}</td></tr>
   </tbody></table>{x.error&&<p className="error">{x.error.code}：{x.error.message}</p>}
   {x.output&&<><p>输入证据：{x.output.evidence.filter((e:any)=>e.source==="input").map((e:any)=>e.quote).join("；")||"无"}</p><p>建议：{x.output.strategy_recommendations.map((r:any)=>r.action).join("；")}</p><p className="muted">这里只显示最终输出，差异不自动等于模型错误；仍需区分规则、检索、模型与后处理。</p></>}
   </details>)}
  </div>}
  <div className="card" style={{marginTop:16}}><h4>历史评测（仅保存评测记录，不计入业务分析量）</h4><button className="secondary" onClick={()=>api<any[]>("/evaluations/runs").then(setHistory).catch(e=>setError(e.message))}>刷新历史</button>{!history.length?<p className="state">尚无评测记录。</p>:history.map(x=><div className="review-item" key={x.run_id}><span>#{x.run_id} · {x.dataset?.name||"旧记录"} · {states[x.status]||x.status} · {x.mode}</span><button className="secondary" disabled={busy||running} onClick={()=>openRun(x.run_id)}>查看逐条结果</button></div>)}</div>
 </>;
}
