"use client";
import { type ReactNode } from "react";

export type Screen = "项目概览" | "单条分析" | "批量分析" | "综合归因" | "业务闭环" | "人工复核" | "评测中心" | "Prompt 与规则" | "项目复盘";
const groups = [
  { label: "工作台", icon: "grid", screens: ["项目概览"] },
  { label: "分析任务", icon: "layers", screens: ["单条分析", "批量分析", "综合归因", "业务闭环"] },
  { label: "人工复核", icon: "check", screens: ["人工复核"] },
  { label: "评测中心", icon: "chart", screens: ["评测中心"] },
  { label: "知识库与配置", icon: "book", screens: ["Prompt 与规则"] },
] as const;
const tabs: Partial<Record<Screen, string>> = { "单条分析": "新建分析", "批量分析": "批量任务", "综合归因": "按广告汇总", "业务闭环": "交接报告" };

function Icon({ name }: { name: string }) {
  const paths: Record<string, ReactNode> = {
    grid: <><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></>,
    layers: <><path d="m12 3 9 5-9 5-9-5 9-5Z"/><path d="m3 12 9 5 9-5M3 16l9 5 9-5"/></>,
    check: <><rect x="4" y="3" width="16" height="18" rx="3"/><path d="m8 12 3 3 5-6"/></>,
    chart: <><path d="M4 3v17h17M8 15v-4M13 15V6M18 15v-7"/></>,
    book: <><path d="M12 5v16M12 5C8 2 3 4 3 4v15s5-2 9 2c4-4 9-2 9-2V4s-5-2-9 1Z"/></>,
    arrow: <path d="M5 12h14m-5-5 5 5-5 5"/>,
  };
  return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name] || paths.grid}</svg>;
}

export function WorkspaceChrome({ page, lastAnalysis, onNavigate, health, healthError, children }: {
  page: Screen; lastAnalysis: Screen; onNavigate: (screen: Screen) => void;
  health?: { mode?: string; provider?: string; model?: string; image_review_enabled?: boolean };
  healthError: string; children: ReactNode;
}) {
  const group = groups.find(g => (g.screens as readonly string[]).includes(page));
  const provider = health?.mode === "provider";
  const navigate = (screen: Screen) => {
    onNavigate(screen);
  };
  return <div className="shell workspace-v2">
    <aside className="sidebar">
      <div className="brand"><div className="brand-lockup"><div className="brand-mark">AE</div><div><h1>广告体验分析助手</h1><p>Ad Experience Insight</p></div></div><span className="workspace-caption">个人作品 / 演示工作空间</span></div>
      <div className="nav-section-label">工作空间</div>
      <nav className="nav" aria-label="主导航">{groups.map(g => <button key={g.label} type="button" aria-current={group?.label === g.label ? "page" : undefined} className={group?.label === g.label ? "active" : ""} onClick={() => navigate(g.label === "分析任务" ? lastAnalysis : g.screens[0])}><Icon name={g.icon}/><span>{g.label}</span>{group?.label === g.label && <span className="nav-active-dot"/>}</button>)}</nav>
      <div className="sidebar-foot"><div className="sidebar-note"><span className="status-dot"/>公开规则 · 合成示例</div><p>AI 建议，仅供辅助判断</p><button type="button" className={`about-link ${page === "项目复盘" ? "active" : ""}`} onClick={() => navigate("项目复盘")}>项目说明与复盘 <span aria-hidden="true">↗</span></button></div>
    </aside>
    <main className="main">
      <header className="topbar"><div className="breadcrumb"><span>工作空间</span><span aria-hidden="true">/</span><h2>{group?.label || "项目说明"}</h2></div><div className="topbar-right"><span className={`connection-label ${healthError ? "offline" : ""}`}><span className="status-dot"/>{healthError ? "服务未连接" : health ? "本地服务已连接" : "连接中"}</span><span className="badge">{provider ? "真实模型模式" : health ? "规则演示模式" : "正在检查服务"}</span></div></header>
      <div className="content">
        <div className="environment-note"><span><span className="note-icon" aria-hidden="true">i</span>个人演示环境 · 使用公开资料、合成示例或自行提供的数据；分析建议不自动执行。</span><details className="environment-detail"><summary>环境详情</summary><div>{healthError || (provider ? `${health?.provider} / ${health?.model} · 本地检索已启用` : "Deterministic Demo Mode · 规则生成可重复结果") }<br/>{health?.image_review_enabled ? "图片审核已启用" : "图片语义审核未启用"}<br/>不接入 vivo 内部系统，不代表真实线上效果或业务收益。</div></details></div>
        {group?.label === "分析任务" && <nav className="module-tabs" aria-label="分析任务视图">{groups[1].screens.map(screen => <button type="button" key={screen} aria-current={page === screen ? "page" : undefined} className={page === screen ? "active" : ""} onClick={() => navigate(screen)}>{tabs[screen]}</button>)}</nav>}
        {children}
        <footer className="workspace-footer"><span>公开依据 · 判断留痕 · 人工确认</span><span>界面版本 2.0 · 前端快照可回滚</span></footer>
      </div>
    </main>
  </div>;
}
