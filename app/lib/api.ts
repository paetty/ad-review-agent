export const API = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000/api";
export async function api<T>(path:string, init?:RequestInit):Promise<T>{
  const response=await fetch(`${API}${path}`,init);
  const data=await response.json().catch(()=>({}));
  if(!response.ok) throw new Error(data?.detail?.message || data?.detail || "请求失败");
  return data as T;
}

