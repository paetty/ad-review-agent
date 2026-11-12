"use client";

import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { api, ApiError, resetApiSession, SESSION_EXPIRED } from "../lib/api";

export type Staff = { employee_id: string; display_name: string; role: "product" | "operations" | "supervisor" };

export function StaffGate({ children }: { children: (staff: Staff, logout: () => Promise<void>) => ReactNode }) {
  const [staff, setStaff] = useState<Staff>();
  const [ready, setReady] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [employeeId, setEmployeeId] = useState("");
  const [password, setPassword] = useState("");

  function connect(signal?: AbortSignal) {
    return api<{enterprise_demo?: boolean}>("/health", {signal}).then(health => {
      if (!health.enterprise_demo) throw Error("当前连接的后端没有启用企业演示。");
      return api<Staff>("/auth/me", {signal});
    }).then(user => {
      setStaff(user);
      setReady(true);
    }).catch(err => {
      if (signal?.aborted) return;
      if (err instanceof ApiError && err.status === 401) {
        setReady(true);
      } else {
        setError(err instanceof Error ? err.message : "无法连接企业演示服务");
      }
    });
  }

  useEffect(() => {
    const controller = new AbortController();
    void connect(controller.signal);
    const expire = () => {
      resetApiSession();
      setStaff(undefined);
      setEmployeeId("");
      setPassword("");
      setError("会话已过期，请重新登录。");
    };
    window.addEventListener(SESSION_EXPIRED, expire);
    return () => {
      controller.abort();
      window.removeEventListener(SESSION_EXPIRED, expire);
    };
  }, []);

  async function login(event: FormEvent) {
    event.preventDefault();
    setError("");
    setLoading(true);
    try {
      const user = await api<Staff>("/auth/login", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({employee_id: employeeId, password}),
      });
      resetApiSession();
      setStaff(user);
    } catch (err) {
      setError(err instanceof Error ? err.message : "登录失败");
    } finally {
      setPassword("");
      setLoading(false);
    }
  }

  async function logout() {
    setLoading(true);
    setError("");
    try {
      await api("/auth/logout", {method: "POST"});
    } catch (err) {
      if (!(err instanceof ApiError && err.status === 401)) {
        setError("暂时无法退出，请确认服务已连接后重试。");
        setLoading(false);
        return;
      }
    }
    resetApiSession();
    setStaff(undefined);
    setEmployeeId("");
    setPassword("");
    setLoading(false);
  }

  if (staff) return <div key={staff.employee_id}>
    {error && <div className="error" role="alert">{error}</div>}
    {children(staff, logout)}
  </div>;
  return <main className="staff-login">
    <section className="card staff-login-card">
      <div className="brand-mark">AE</div>
      <span className="eyebrow">企业演示 · SYNTHETIC DEMO</span>
      <h1>广告治理工作台</h1>
      <p className="muted">使用预置的模拟工号和密码登录。</p>
      {error && <p className="error" role="alert">{error}</p>}
      {!ready ? <button className="secondary" onClick={() => {setError("");void connect()}}>检查服务连接</button> :
        <form onSubmit={login}>
          <label className="field">模拟工号<input required maxLength={32} autoComplete="username" value={employeeId} onChange={event => setEmployeeId(event.target.value)}/></label>
          <label className="field">密码<input required maxLength={128} type="password" autoComplete="current-password" value={password} onChange={event => setPassword(event.target.value)}/></label>
          <button className="primary" disabled={loading}>{loading ? "正在登录…" : "登录工作台"}</button>
        </form>}
    </section>
  </main>;
}
