"use client";

import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../lib/api";

type RiskTrends = {
  analysis_count: number;
  high_risk_count: number;
  pending_review_count: number;
  trend: { date: string; analyses: number; high_risk: number }[];
};

export function WorkspaceRiskTrend({ data }: { data: RiskTrends }) {
  return <section className="staff-section" aria-labelledby="workspace-risk-trend">
    <div className="grid three">
      {[
        ["近 7 天分析量", data.analysis_count, "按原始分析记录计数"],
        ["近 7 天高风险分析量", data.high_risk_count, "原始风险为高或极高"],
        ["当前待复核分析数", data.pending_review_count, "按尚未完成复核的分析去重"],
      ].map(([label, count, note]) => <div key={label} className="card metric-card">
        <div className="metric-label">{label}</div>
        <div className="metric-value" aria-label={String(label)}>{count}</div>
        <div className="metric-sub">{note}</div>
      </div>)}
    </div>
    <div className="card staff-section">
      <h4 id="workspace-risk-trend">近 7 天分析风险趋势</h4>
      <p className="muted">按自然日统计（UTC+8）。高风险分析量包含在分析量中。</p>
      {data.analysis_count ? <div style={{height:250}}><ResponsiveContainer>
        <BarChart data={data.trend}>
          <CartesianGrid strokeDasharray="3 3" vertical={false}/>
          <XAxis dataKey="date" tickFormatter={value => value.slice(5)}/>
          <YAxis allowDecimals={false}/><Tooltip/><Legend/>
          <Bar dataKey="analyses" name="分析量" fill="#7d9aba" radius={[4,4,0,0]} isAnimationActive={false}/>
          <Bar dataKey="high_risk" name="高风险分析量" fill="#b58277" radius={[4,4,0,0]} isAnimationActive={false}/>
        </BarChart>
      </ResponsiveContainer></div> : <div className="state">近 7 天暂无分析记录。</div>}
    </div>
  </section>;
}

const sourceNames = {
  regulatory: "监管动态",
  peer_platform: "同业公开案例",
  synthetic_demo: "模拟观察",
};

type SourceType = keyof typeof sourceNames;
type Policy = {
  id: string; title: string; source_type: SourceType; publisher: string; source_url: string | null;
  published: string | null; effective: string | null; scope: string; action: string; status: string;
};

type DateWindow = { start: number; end: number };
const dayMs = 86_400_000;
const shanghaiDay = () => Math.floor((Date.now() + 8 * 60 * 60 * 1000) / dayMs);
const dateFilters = [
  {value:"all", label:"全部时间"},
  {value:"week", label:"近一周"},
  {value:"halfYear", label:"近半年"},
  {value:"year", label:"近一年"},
  {value:"custom", label:"自定义日期"},
  {value:"undated", label:"日期未标注"},
] as const;
type DateFilter = typeof dateFilters[number]["value"];

const dayNumber = (date: string) => Date.parse(`${date}T00:00:00Z`) / dayMs;
const dateText = (day: number) => new Date(day * dayMs).toISOString().slice(0, 10);

function shiftMonths(day: number, months: number) {
  const date = new Date(day * dayMs);
  const first = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth() + months, 1));
  const lastDay = new Date(Date.UTC(first.getUTCFullYear(), first.getUTCMonth() + 1, 0)).getUTCDate();
  return first.getTime() / dayMs + Math.min(date.getUTCDate(), lastDay) - 1;
}

function publicationWindow(published: string | null): DateWindow | undefined {
  if (!published) return;
  const monthOnly = /^\d{4}-\d{2}$/.test(published);
  const start = dayNumber(monthOnly ? `${published}-01` : published);
  if (!Number.isFinite(start)) return;
  return {start, end: monthOnly ? shiftMonths(start, 1) - 1 : start};
}

export function IndustryWatch() {
  const [policies, setPolicies] = useState<Policy[]>();
  const [error, setError] = useState("");
  const [source, setSource] = useState<SourceType | "all">("all");
  const [dateFilter, setDateFilter] = useState<DateFilter>("all");
  const [today, setToday] = useState(shanghaiDay);
  const [customDates, setCustomDates] = useState<DateWindow>();
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    api<Policy[]>("/enterprise/policy-watch", {signal:controller.signal}).then(setPolicies).catch(err => {
      if (!controller.signal.aborted) setError(err.message);
    });
    return () => controller.abort();
  }, [attempt]);
  const year = {start:shiftMonths(today, -12), end:today};
  const presets = {
    week:{start:today - 6, end:today},
    halfYear:{start:shiftMonths(today, -6), end:today},
    year,
  };
  const publications = (policies || []).map(policy => ({policy, dates:publicationWindow(policy.published)}));
  const activeRange = dateFilter === "custom" ? customDates : dateFilter === "all" || dateFilter === "undated" ? undefined : presets[dateFilter];
  const firstDay = Math.min(year.start, ...publications.map(({dates}) => dates?.start ?? year.start));
  const lastDay = Math.max(today, ...publications.map(({dates}) => dates?.end ?? today));
  const visible = publications.filter(({policy,dates}) => {
    if (source !== "all" && policy.source_type !== source) return false;
    if (dateFilter === "undated") return !dates;
    return !activeRange || !!dates && dates.start <= activeRange.end && dates.end >= activeRange.start;
  });

  function selectDates(value: DateFilter) {
    setToday(shanghaiDay());
    if (value === "custom") setCustomDates(customDates ?? activeRange ?? year);
    setDateFilter(value);
  }

  function updateBoundary(edge: keyof DateWindow, value: number) {
    if (!Number.isFinite(value)) return;
    const day = Math.min(lastDay, Math.max(firstDay, value));
    setCustomDates(previous => {
      const range = previous ?? year;
      return edge === "start"
        ? {start:day,end:Math.max(day, range.end)}
        : {start:Math.min(day, range.start),end:day};
    });
  }
  return <>
    <div className="hero"><div>
      <div className="eyebrow">INDUSTRY WATCH</div>
      <h3>行业规范动态</h3>
      <p>人工整理广告监管动态和同业审核案例，供团队评估风险、准备抽查和讨论策略。</p>
    </div></div>
    <div className="environment-note">资讯供参考，与当前知识库分开维护。是否纳入核查流程，由团队结合业务场景评估。</div>
    <label className="field staff-section" style={{maxWidth:240}}>资料类型
      <select value={source} onChange={event => setSource(event.target.value as SourceType | "all")}>
        <option value="all">全部资料</option>
        {Object.entries(sourceNames).map(([value, label]) => <option value={value} key={value}>{label}</option>)}
      </select>
    </label>
    {policies && <div className="staff-section">
      <p className="muted" id="publication-filter-label">发布时间</p>
      <div className="actions" role="group" aria-labelledby="publication-filter-label">
        {dateFilters.filter(({value}) => value !== "undated" || publications.some(({dates}) => !dates))
          .map(({value,label}) => <button type="button" key={value}
          className={dateFilter === value ? "primary" : "secondary"}
          aria-pressed={dateFilter === value} onClick={() => selectDates(value)}>{label}</button>)}
      </div>
      {dateFilter === "custom" && customDates && <div className="card grid two staff-section">
        {([["start","开始日期"],["end","结束日期"]] as const).map(([edge,label]) => <div key={edge}>
          <label className="field">{label}
            <input type="date" min={dateText(firstDay)} max={dateText(lastDay)} value={dateText(customDates[edge])}
              onChange={event => updateBoundary(edge, dayNumber(event.target.value))}/>
          </label>
          <input className="policy-date-slider" type="range" min={firstDay} max={lastDay}
            value={customDates[edge]} aria-label={`拖动${label}`} aria-valuetext={dateText(customDates[edge])}
            onChange={event => updateBoundary(edge, event.target.valueAsNumber)}/>
        </div>)}
      </div>}
      {activeRange && <p className="muted">筛选范围 {dateText(activeRange.start)} 至 {dateText(activeRange.end)}（含起止日期）</p>}
      <p className="muted">按公布或发布时间筛选。仅标注月份的资料按该月覆盖范围匹配，生效日期在卡片中单列。</p>
    </div>}
    {error ? <div className="error staff-section" role="alert">加载失败：{error} <button className="text-button" onClick={() => {setError("");setAttempt(value => value + 1)}}>重试</button></div>
      : !policies ? <div className="card state staff-section">正在读取行业资料…</div>
      : !visible.length ? <div className="card state staff-section">暂无符合所选类型和时间的资料。</div>
      : <div className="grid two staff-section">{visible.map(({policy}) => <article key={policy.id} className="card policy-watch-card">
        <span className="subtle-badge">{sourceNames[policy.source_type]}</span>
        <h4>{policy.title}</h4>
        <p className="muted">{[policy.publisher, policy.published, policy.effective && `生效 ${policy.effective}`].filter(Boolean).join(" · ")}</p>
        <p><strong>关注范围</strong> {policy.scope}</p>
        <p><strong>可参考的动作</strong> {policy.action}</p>
        <p className="muted">{policy.status}</p>
        {policy.source_url && <a href={policy.source_url} target="_blank" rel="noreferrer">查看发布方资料 ↗</a>}
      </article>)}</div>}
  </>;
}
