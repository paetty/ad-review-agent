"use client";

import { useState, type FormEvent } from "react";
import { api, API } from "../lib/api";

type Kind = "monitor" | "strategy";
type Advice = { action: string; evidence_ids: string[] };
type BaseResult = {
  status: string; source: "synthetic" | "provided"; rows: number; mode: "rules" | "provider";
  prompt_version: string; model_notice?: string; model?: string;
  planning_mode?: "rules" | "provider";
  industry?: string | null; min_impressions: number | null; inclusive: boolean;
  model_summary: { summary: string; recommendations: Advice[] } | null;
};
type Metrics = {
  days: number; impressions: number; revenue: number | null; spend: number | null; ecpm: number | null;
  payer_rate: number | null; feedback_rate: number | null; negative_feedback: number | null;
  paying_users: number | null; eligible_users: number | null;
};
type History = {start:string|null; end:string|null; days:number; rate:number|null; delta:number|null};
type MonitorResult = BaseResult & {
  start: string; end: string; skipped: number; flagged: number; feedback_threshold: number;
  history_summary: (History & {current_rate:number|null}) | null;
  items: { ad_id: string; creative_id: string; evidence_id: string; metrics: Metrics; risk: string | null;
    industry?: string; history: History | null;
    flagged: boolean; findings: string[]; label_names: string[]; quotes: string[]; recommendation: string;
    citations: {chunk_id: string; document_title: string; snippet: string; source_url?: string | null}[];
  }[];
};
type StrategyResult = BaseResult & {
  before: Metrics; after: Metrics; dates: Record<PeriodField, string>; expected_days: [number,number]; excluded_rows: number;
  common_materials: number; target_drop: number; guardrail_drop: number; notes: string[]; guardrails: string[];
  recommendation: string; target_met: boolean; comparable: boolean;
  comparisons: { evidence_id: string; title: string; metric: string; unit: "count" | "money" | "percent";
    before: number | null; after: number | null; delta: number | null; relative: number | null }[];
};
const emptyPeriods = {launch_date:"",before_start:"",before_end:"",after_start:"",after_end:""};
type PeriodField = keyof typeof emptyPeriods;
const exampleQuestions: Record<Kind,string> = {
  monitor: "请检查电商行业最近3天曝光量大于一万的素材，比较反馈事件率是否高于历史平均，给出证据和核查建议。",
  strategy: "请分析上线前后的反馈事件率、日均收入和 eCPM。反馈事件率目标降幅为10%，商业护栏降幅为10%。",
};

const number = (value: number | null, digits = 2) =>
  value === null ? "不可计算" : value.toLocaleString("zh-CN", {maximumFractionDigits:digits});
const percent = (value: number | null) => value === null ? "不可计算" : `${number(value)}%`;
const change = (value: number | null, suffix: string) => value === null ? "不可计算" : `${value > 0 ? "+" : ""}${number(value)}${suffix}`;
const scope = (result:BaseResult) => [
  result.industry ? `行业 ${result.industry}` : "全部行业",
  result.min_impressions === null ? "全部曝光量" : `曝光${result.inclusive ? "至少" : "大于"} ${number(result.min_impressions,0)}`,
].join(" · ");

function ResultSummary({ result }: {result: BaseResult}) {
  return <>
    <div className="section-heading">
      <div><h4>{result.status}</h4><p className="muted">{result.source === "synthetic" ? "合成演示" : "上传数据"} · {result.rows} 行 · {result.prompt_version}</p></div>
      <span className="badge">{result.mode === "provider" ? result.model || "真实模型摘要" : "程序计算＋规则建议"}</span>
    </div>
    {result.model_notice && <p className="muted">{result.model_notice}</p>}
    {result.planning_mode === "rules" && result.mode === "provider" && <p className="muted">条件由本地规则提取，摘要由模型整理。</p>}
  </>;
}

function HistoryLine({history}:{history:History}) {
  if (history.delta === null) return <p className="muted">历史对比不可计算。请核对当前和历史日期覆盖、反馈事件数与曝光分母。</p>;
  return <p className="muted">历史 {history.start} 至 {history.end} · {history.days} 天 · 反馈事件率 {percent(history.rate)} · 当前较历史 {change(history.delta," 个百分点")}</p>;
}

function ModelAdvice({result}:{result: BaseResult}) {
  if (!result.model_summary) return null;
  return <section className="card staff-section">
    <h4>AI 摘要与建议</h4>
    <p>{result.model_summary.summary}</p>
    <ul>{result.model_summary.recommendations.map((item,index) =>
      <li key={index}>{item.action} <span className="muted">依据 {item.evidence_ids.join("、")}</span></li>
    )}</ul>
  </section>;
}

function MonitorView({result}:{result:MonitorResult}) {
  return <>
    <section className="card staff-section" aria-label="日常检测结果">
      <ResultSummary result={result}/>
      <p>{result.start} 至 {result.end} · {scope(result)} · 符合 {result.items.length} 个 · 待核查 {result.flagged} 个 · 曝光筛除 {result.skipped} 个</p>
      {result.history_summary && <div className="evidence">
        <strong>D01 · 入选素材的反馈事件率</strong> 当前 {percent(result.history_summary.current_rate)}
        <HistoryLine history={result.history_summary}/>
      </div>}
      <p className="muted">反馈事件率达到 {percent(result.feedback_threshold)} 且至少有 3 条反馈事件时提示核查。每行可展开查看证据和建议。</p>
      {!result.items.length && <div className="state">当前数据没有素材达到曝光筛选条件。</div>}
      {result.items.map(item => <details className="disclosure" key={item.evidence_id} open={item.flagged || undefined}>
        <summary>{item.evidence_id} · {item.ad_id}{item.creative_id ? ` / ${item.creative_id}` : " / 广告级"} · {number(item.metrics.impressions,0)} 曝光 · {item.flagged ? "待核查" : "未触发核查"}</summary>
        <p>{item.findings.join(" · ") || "现有输入未达到设定的核查条件。"}</p>
        <p className="muted">反馈事件 {number(item.metrics.negative_feedback,0)} · 反馈事件率 {percent(item.metrics.feedback_rate)} · eCPM {number(item.metrics.ecpm)} · 收入 {number(item.metrics.revenue)} · 消耗 {number(item.metrics.spend)} · 付款人率 {percent(item.metrics.payer_rate)}</p>
        {item.history && <HistoryLine history={item.history}/>}
        {item.label_names.length > 0 && <p className="muted">文字标签 {item.label_names.join("、")}</p>}
        {item.quotes.map((quote,index) => <blockquote key={index}>{quote}</blockquote>)}
        {item.citations.length > 0 && <details className="disclosure"><summary>相关参考资料</summary>
          {item.citations.map(citation => <p key={citation.chunk_id}><strong>{citation.document_title}</strong> {citation.snippet} {citation.source_url && <a href={citation.source_url} target="_blank" rel="noreferrer">查看来源</a>}</p>)}
        </details>}
        <p><strong>建议</strong> {item.recommendation}</p>
      </details>)}
    </section>
    <ModelAdvice result={result}/>
  </>;
}

function StrategyView({result}:{result:StrategyResult}) {
  const unitValue = (value:number|null, unit:StrategyResult["comparisons"][number]["unit"]) =>
    unit === "percent" ? percent(value) : number(value);
  return <>
    <section className="card staff-section" aria-label="策略效果结果">
      <ResultSummary result={result}/>
      <p><strong>下一步</strong> {result.recommendation}</p>
      <p className="muted">{scope(result)}{result.min_impressions !== null && "（两个观察周期合计）"}</p>
      <p className="muted">上线 {result.dates.launch_date} · 前 {result.dates.before_start} 至 {result.dates.before_end} · 后 {result.dates.after_start} 至 {result.dates.after_end}。两段均按自然日纳入。</p>
      <p className="muted">D01 · 覆盖前 {result.before.days}/{result.expected_days[0]} 天、后 {result.after.days}/{result.expected_days[1]} 天 · 共同广告或素材 {result.common_materials} 个 · 未纳入对比 {result.excluded_rows} 行</p>
      <p className="muted">前后曝光 {number(result.before.impressions,0)} → {number(result.after.impressions,0)} · 反馈事件 {number(result.before.negative_feedback,0)} → {number(result.after.negative_feedback,0)} · 收入 {number(result.before.revenue)} → {number(result.after.revenue)} · 消耗 {number(result.before.spend)} → {number(result.after.spend)}</p>
      {result.notes.map(note => <p className="error" key={note}>{note}</p>)}
      <div className="table-wrap"><table>
        <thead><tr><th>证据 / 指标</th><th>上线前</th><th>上线后</th><th>差值</th><th>相对变化</th><th>检查</th></tr></thead>
        <tbody>{result.comparisons.map(item => <tr key={item.evidence_id}>
          <td>{item.evidence_id} · {item.title}</td>
          <td>{unitValue(item.before,item.unit)}</td><td>{unitValue(item.after,item.unit)}</td>
          <td>{change(item.delta,item.unit === "percent" ? " 个百分点" : "")}</td>
          <td>{change(item.relative,"%")}</td>
          <td>{result.guardrails.includes(item.evidence_id) ? (result.comparable ? "触发护栏" : "候选告警，待核对") :
            item.metric === "feedback_rate" ? item.relative === null ? "目标无法计算" : result.target_met ? "达到目标" : "未达到目标" : "—"}</td>
        </tr>)}</tbody>
      </table></div>
      <p className="muted">反馈事件率目标为相对下降至少 {percent(result.target_drop)}。日均收入、eCPM 或付款人率相对下降达到 {percent(result.guardrail_drop)} 时提示核查。</p>
      <p className="muted">前后对比描述观察到的变化。广告供给、活动、流量和同期改动都可能影响指标，策略归因需要对照验证。</p>
    </section>
    <ModelAdvice result={result}/>
  </>;
}

export function DiagnosticsWorkspace({kind}:{kind:Kind}) {
  const strategy = kind === "strategy";
  const [file,setFile] = useState<File>();
  const [busy,setBusy] = useState(false);
  const [error,setError] = useState("");
  const [result,setResult] = useState<MonitorResult | StrategyResult>();
  const [periods,setPeriods] = useState(emptyPeriods);
  const [question,setQuestion] = useState("");

  async function run(sample:boolean) {
    if (busy) return;
    setBusy(true);
    setError("");
    setResult(undefined);
    try {
      const body = new FormData();
      if (!sample && file) body.append("file",file);
      const request = question.trim() || (sample ? exampleQuestions[kind] : "");
      if (sample && !question.trim()) setQuestion(request);
      body.set("analysis_request",request);
      if (strategy) {
        const selected = sample ? await api<typeof periods>("/diagnostics/sample-periods") : periods;
        if (sample) setPeriods(selected);
        Object.entries(selected).forEach(([key,value])=>body.set(key,value));
      }
      setResult(await api<MonitorResult | StrategyResult>(`/diagnostics/${kind}`,{method:"POST",body}));
    } catch (err) {
      setError(err instanceof Error ? err.message : "检测未完成");
    } finally {
      setBusy(false);
    }
  }

  function submit(event:FormEvent) {
    event.preventDefault();
    if (file && question.trim()) void run(false);
  }

  return <>
    <div className="hero"><div>
      <h3>{strategy ? "策略效果检测" : "日常安全检测"}</h3>
    </div><a className="secondary" href={`${API}/diagnostics/template`}>下载合成 CSV 模板</a></div>
    <form className="card" onSubmit={submit}>
      <fieldset disabled={busy} className="diagnostics-fields">
        <div className="grid two diagnostics-inputs">
          <div>
            <label className="field">你想如何分析这个文件？
              <textarea rows={6} required maxLength={600} value={question} placeholder={exampleQuestions[kind]} onChange={event=>setQuestion(event.target.value)}/>
            </label>
            <button type="button" className="text-button" onClick={()=>setQuestion(exampleQuestions[kind])}>填入示例要求</button>
          </div>
          <div>
            <label className="field">日指标 CSV<input type="file" accept=".csv,text/csv" onChange={event=>setFile(event.target.files?.[0])}/></label>
            <p className="muted">每行对应一天和一个广告或素材。UTF-8 CSV，最多 200 行、2 MB。</p>
            {strategy && <div className="diagnostics-periods">
              <label className="field">策略上线日期<input type="date" required value={periods.launch_date} onChange={event=>setPeriods(old=>({...old,launch_date:event.target.value}))}/></label>
              {([["上线前观察周期","before_start","before_end"],["上线后观察周期","after_start","after_end"]] as const).map(([label,start,end])=>
                <fieldset className="diagnostics-fields" key={start}>
                  <legend>{label}</legend>
                  <div className="diagnostics-range">
                    <input aria-label={label+"开始"} type="date" required value={periods[start]} onChange={event=>setPeriods(old=>({...old,[start]:event.target.value}))}/>
                    <span aria-hidden="true">至</span>
                    <input aria-label={label+"结束"} type="date" required value={periods[end]} onChange={event=>setPeriods(old=>({...old,[end]:event.target.value}))}/>
                  </div>
                </fieldset>)}
            </div>}
          </div>
        </div>
        <p className="muted">提交后，已配置的模型会处理分析要求和结构化证据。原始 CSV 与素材原文在本机处理。</p>
        <div className="actions"><button className="primary" type="submit" disabled={!file||!question.trim()||busy}>{busy?"分析中…":"检测上传数据"}</button>
          <button className="secondary" type="button" disabled={busy} onClick={()=>void run(true)}>运行合成示例</button></div>
      </fieldset>
    </form>
    {error && <p className="error staff-section" role="alert">{error}</p>}
    {result && ("items" in result ? <MonitorView result={result}/> : <StrategyView result={result}/>)}
  </>;
}
