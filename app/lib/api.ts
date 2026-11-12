export const ENTERPRISE_DEMO = process.env.NEXT_PUBLIC_ENTERPRISE_DEMO === "1";
export const API = process.env.NEXT_PUBLIC_API_URL || (ENTERPRISE_DEMO ? "http://localhost:8016/api" : "http://127.0.0.1:8000/api");
export const SESSION_EXPIRED = "enterprise-session-expired";
let sessionGeneration = 0;

export function resetApiSession() {
  sessionGeneration += 1;
}

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

export async function api<T>(path:string, init?:RequestInit):Promise<T>{
  const generation = sessionGeneration;
  const response=await fetch(`${API}${path}`,ENTERPRISE_DEMO ? {...init, credentials:"include", cache:"no-store"} : init);
  const data=await response.json().catch(()=>({}));
  if(!response.ok) {
    if(ENTERPRISE_DEMO && response.status===401 && !path.startsWith("/auth/") && generation===sessionGeneration) {
      window.dispatchEvent(new Event(SESSION_EXPIRED));
    }
    throw new ApiError(response.status, data?.detail?.message || (typeof data?.detail==="string" ? data.detail : "请求失败"));
  }
  return data as T;
}

