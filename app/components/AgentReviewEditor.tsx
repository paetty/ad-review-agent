"use client";
import { useState } from "react";
import { suggestRecommendationLabels, recommendationIsActive } from "../lib/review-recommendations";

type Recommendation={category:string;action:string;rationale:string;priority:string;expected_metric:string;guardrail_metric:string};
type Output={labels:{label:string}[];overall_risk:string;strategy_recommendations:Recommendation[]};
export function AgentReviewEditor({output,names,busy,onSave,onCancel}:{output:Output;names:Record<string,string>;busy:boolean;onSave:(payload:Record<string,unknown>)=>Promise<void>;onCancel:()=>void}){
 const [labels,setLabels]=useState(output.labels.map(x=>x.label));
 const [risk,setRisk]=useState(output.overall_risk);
 const [recommendations,setRecommendations]=useState(output.strategy_recommendations.map(x=>({...x})));
 const [links,setLinks]=useState(()=>output.strategy_recommendations.map(r=>suggestRecommendationLabels(r,output.labels.map(x=>x.label))));
 const [deleted,setDeleted]=useState<number[]>([]);
 const [notes,setNotes]=useState("");
 const [error,setError]=useState("");
 function toggle(label:string){setLabels(prev=>prev.includes(label)?prev.filter(x=>x!==label):label==="no_issue"?[label]:[...prev.filter(x=>x!=="no_issue"),label]);}
 async function save(){
  const pending=recommendations.some((_,i)=>!deleted.includes(i)&&links[i].length===0);
  const kept=recommendations.map((r,i)=>({r,i})).filter(({i})=>!deleted.includes(i)&&recommendationIsActive(links[i],labels));
  if(pending){setError("有建议尚未确认关联标签，请选择适用标签或删除该建议。");return;}
  if(!labels.length||!kept.length||kept.some(({r})=>!r.action.trim())){setError("请选择至少一个标签，并保留至少一条有效建议；也可以新增建议。");return;}
  setError("");
  await onSave({decision:"modified",corrected_labels:labels,corrected_risk:risk,edited_recommendations:kept.map(({r})=>r),recommendation_label_links:kept.map(({i})=>links[i].filter(x=>labels.includes(x))),notes});
 }
 return <section className="card" aria-label="人工修正表单">
  <h4>编辑人工修正版</h4><p className="muted">原始AI结果保留；保存后继续任务。人工修改不会自动训练模型。</p>
  <fieldset disabled={busy}><legend>体验标签</legend>{Object.entries(names).map(([key,name])=><label key={key} style={{display:"inline-block",margin:8}}><input type="checkbox" checked={labels.includes(key)} onChange={()=>toggle(key)}/>{name}</label>)}</fieldset>
  <label>风险等级 <select disabled={busy} value={risk} onChange={e=>setRisk(e.target.value)}>{["low","medium","high","critical"].map(x=><option key={x}>{x}</option>)}</select></label>
  <p className="muted">建议与标签关联由文字匹配预填，请人工核对。取消标签后，无关联的建议将自动移出修正版；无法识别的建议必须手动关联或删除。只修改备注不会改变标签与建议。</p>
  {recommendations.map((r,i)=>{const active=!deleted.includes(i)&&recommendationIsActive(links[i],labels);return <div key={i} style={{marginTop:12,padding:12,border:"1px solid #d5dce5",borderRadius:8}}>
   <b>{deleted.includes(i)?"已手动删除":!links[i].length?"待确认关联":active?"将保留":"随标签移除，不会保存"} · 建议 {i+1}</b>
   <fieldset disabled={busy||deleted.includes(i)}><legend>适用标签（人工确认）</legend>{Object.entries(names).filter(([key])=>labels.includes(key)||links[i].includes(key)).map(([key,name])=><label key={key} style={{display:"inline-block",margin:6}}><input type="checkbox" checked={links[i].includes(key)} onChange={()=>setLinks(prev=>prev.map((xs,j)=>j===i?xs.includes(key)?xs.filter(x=>x!==key):[...xs,key]:xs))}/>{name}</label>)}</fieldset>
   <label className="field">处理建议<textarea disabled={busy||!active} value={r.action} onChange={e=>setRecommendations(prev=>prev.map((x,j)=>j===i?{...x,action:e.target.value}:x))}/></label><label className="field">建议理由<textarea disabled={busy||!active} value={r.rationale} onChange={e=>setRecommendations(prev=>prev.map((x,j)=>j===i?{...x,rationale:e.target.value}:x))}/></label>
   <button className="secondary" disabled={busy} onClick={()=>setDeleted(prev=>prev.includes(i)?prev.filter(x=>x!==i):[...prev,i])}>{deleted.includes(i)?"恢复建议":"删除建议"}</button>
  </div>})}
  <button className="secondary" disabled={busy||!labels.length} onClick={()=>{setRecommendations(prev=>[...prev,{category:"review",action:"",rationale:"人工补充建议",priority:"P1",expected_metric:"待人工确认",guardrail_metric:"待人工确认"}]);setLinks(prev=>[...prev,[...labels]])}}>新增建议</button>
  <label className="field">修改原因或备注<textarea maxLength={2000} disabled={busy} value={notes} onChange={e=>setNotes(e.target.value)}/></label>
  {error&&<p className="error">{error}</p>}<div className="actions"><button className="primary" disabled={busy} onClick={save}>保存修正并继续</button><button className="secondary" disabled={busy} onClick={onCancel}>取消修改</button></div>
 </section>;
}
