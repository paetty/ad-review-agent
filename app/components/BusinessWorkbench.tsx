"use client";
/* eslint-disable @typescript-eslint/no-explicit-any */
import { useState } from "react";
import { API, api } from "../lib/api";
import { resultLabelName } from "../lib/assessment";

const labels: Record<string, string> = {
  forced_or_unexpected_jump: "非预期跳转", malicious_or_suspicious_redirect: "可疑重定向",
  misleading_claim: "误导宣传", vulgar_or_inappropriate_content: "不适内容", excessive_ad_frequency: "频率过高",
  repetitive_material: "素材重复", unclear_material: "素材不清晰", stale_material: "素材陈旧",
  weak_first_three_seconds: "前三秒信息不足", irrelevant_targeting: "相关性弱", return_path_friction: "返回困难",
  potential_privacy_risk: "隐私风险", no_issue: "未发现明确问题",
};
const statuses: Record<string,string> = { awaiting_review: "待人工核查", needs_information: "待补充信息", draft_ready: "草稿已生成", human_reviewed: "已人工复核" };

export function BusinessWorkbench() {
  const [report, setReport] = useState<any>();
  const [feedback, setFeedback] = useState<File>();
  const [exposures, setExposures] = useState<File>();
  const [source, setSource] = useState("synthetic");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function run(demo: boolean) {
    setBusy(true); setError("");
    try {
      if (demo) {
        const payload = await api("/business/demo-input");
        setReport(await api("/business/reports", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }));
      } else if (feedback) {
        const body = new FormData(); body.append("feedback_file", feedback); body.append("dataset_source", source);
        if (exposures) body.append("exposure_file", exposures);
        setReport(await api("/business/reports/upload", {method:"POST",body}));
      }
    } catch (e:any) { setError(e.message); } finally { setBusy(false); }
  }
  return <>
    <div className="hero"><div><h3>反馈表到部门交接报告</h3><p>区分用户报告、待核验证据和人工结论。按广告、素材、场景、平台和时间窗关联曝光。</p></div><button className="primary" disabled={busy} onClick={()=>run(true)}>{busy ? "分析中…" : "运行配套模拟案例"}</button></div>
    <div className="card"><h4>上传配套表格</h4><p>Excel请另存为UTF-8 CSV。曝光表可选，缺少时不计算比率。每表最多200行。</p>
      <div className="form-grid"><label>反馈表<input type="file" accept=".csv" onChange={e=>setFeedback(e.target.files?.[0])}/></label><label>曝光汇总表<input type="file" accept=".csv" onChange={e=>setExposures(e.target.files?.[0])}/></label>
      <label>数据来源<select value={source} onChange={e=>setSource(e.target.value)}><option value="synthetic">合成演示数据</option><option value="provided">自行提供的脱敏数据</option></select></label></div>
      <div className="actions"><button className="primary" disabled={busy||!feedback} onClick={()=>run(false)}>生成报告</button><a className="secondary" href={`${API}/business/template?kind=feedback`}>下载模拟反馈表</a><a className="secondary" href={`${API}/business/template?kind=exposures`}>下载模拟曝光表</a></div>
    </div>
    {error&&<div className="error">{error}</div>}
    {report&&<>
      <div className="grid four" style={{marginTop:16}}>{[["反馈事件",report.summary.feedback_rows],["问题单",report.summary.cases],["待核查",report.summary.pending_review],["已复核",report.summary.human_reviewed]].map(([name,value])=><div className="card" key={String(name)}><div className="metric-label">{name}</div><div className="metric-value">{value}</div></div>)}</div>
      <div className="card" style={{marginTop:16}}><p>来源：{report.dataset_source}；本次实测处理耗时 {report.elapsed_ms_measured}ms。耗时包含当前分析流程，不代表已测真实模型。</p><p>{report.metric_boundary}</p>
        <div className="actions"><a className="secondary" href={`${API}/business/reports/${report.report_id}/export`}>导出草稿</a>{report.summary.handoff_ready?<a className="primary" href={`${API}/business/reports/${report.report_id}/export?final=true`}>导出交接报告</a>:<span className="muted">全部必要核查完成后可导出交接报告</span>}</div><p className="muted">导出不会发送给部门，也不会修改投放策略。复核通过不代表问题已经解决。</p>
      </div>
      {report.cases.map((item:any)=><CaseReview key={`${report.report_id}-${item.case_id}`} item={item} reportId={report.report_id} update={setReport}/>)}
    </>}
  </>;
}

function CaseReview({item,reportId,update}:{item:any;reportId:string;update:(r:any)=>void}) {
  const [decision,setDecision]=useState("accepted");
  const [notes,setNotes]=useState("");
  const [confirmed,setConfirmed]=useState(false);
  const [risk,setRisk]=useState(item.effective_risk);
  const [selected,setSelected]=useState<string[]>(item.effective_labels);
  const [error,setError]=useState("");
  const [busy,setBusy]=useState(false);
  async function save(e:React.FormEvent) {
    e.preventDefault();setBusy(true);setError("");
    try {
      update(await api(`/business/reports/${reportId}/cases/${item.case_id}/review`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({decision,notes,evidence_confirmed:confirmed,...(decision==="modified"?{corrected_labels:selected,corrected_risk:risk}:{})})}));
    }catch(e:any){setError(e.message)}finally{setBusy(false)}
  }
  return <div className="card" style={{marginTop:16}}>
    <h4>{item.ad_id} / {item.creative_id} · {statuses[item.handoff_status]}</h4><p>{item.media_scene} · {item.platform} · {item.window_start} 至 {item.window_end}</p>
    <div className="pill-row"><span className={`risk ${item.effective_risk}`}>{item.effective_risk}</span>{item.effective_labels.map((x:string)=><span className="label" key={x}>{resultLabelName(x,item.assessment_status,labels)}</span>)}</div>
    {item.assessment_status==="insufficient_evidence"&&<p className="error">原始分析：证据不足，不能据此判断素材正常。</p>}
    <p>建议交接：{item.suggested_owners.join("、")}</p><p>每万曝光反馈事件数：{item.rate.feedback_events_per_10k_impressions??`不可计算（${item.rate.unavailable_reason}）`}</p>
    {item.observations.map((x:any)=><div className="evidence" key={x.feedback_id}>用户报告（尚未经系统核实）：{x.user_report}</div>)}
    {item.missing_information.map((x:string)=><p key={x}>原始待补信息：{x}</p>)}
    <details><summary>素材核查清单与规则来源</summary>{item.media_checks.map((x:any,i:number)=><p key={i}>{x.material_format} / {x.landing_type}：{x.checks.join("；")||"暂无对应的自动核查"}</p>)}<p className="muted">当前只生成清单，没有自动播放视频、执行OCR或打开落地页。</p>{item.citations.map((x:any)=><div className="evidence" key={x.chunk_id}>{x.document_title} · {x.source_type} · {x.content_type}<p>{x.snippet}</p>{x.source_url&&<a href={x.source_url} target="_blank" rel="noreferrer">查看发布方原文</a>}</div>)}</details>
    <details><summary>人工核查与修正</summary><form onSubmit={save}><label>处理方式<select value={decision} onChange={e=>setDecision(e.target.value)}><option value="accepted">核验后接受原结论</option><option value="modified">核验后修正结论</option><option value="request_info">请求补充信息</option></select></label>
      {decision==="modified"&&<><label>修正风险<select value={risk} onChange={e=>setRisk(e.target.value)}>{["low","medium","high","critical"].map(x=><option key={x}>{x}</option>)}</select></label><div className="pill-row">{Object.entries(labels).map(([key,name])=><label key={key}><input type="checkbox" checked={selected.includes(key)} onChange={e=>setSelected(e.target.checked?key==="no_issue"?[key]:[...selected.filter(x=>x!=="no_issue"),key]:selected.filter(x=>x!==key))}/>{name}</label>)}</div></>}
      <label>核查证据、修改原因或待补信息<textarea required minLength={3} maxLength={2000} value={notes} onChange={e=>setNotes(e.target.value)}/></label><label><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/>我已完成本条所需的人工核查（补充信息时无需勾选）</label>
      {error&&<div className="error">{error}</div>}<button className="primary" disabled={busy}>保存复核记录</button></form></details>
    {item.review_history.length>0&&<p>最新人工备注：{item.review_history[item.review_history.length-1].notes}。原始反馈与分析保持留存。</p>}
  </div>;
}
