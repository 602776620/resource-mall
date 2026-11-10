/**
 * 认证状态（07 §1 stores/：token 落 localStorage，user 存内存）。
 * 红线：仅本模块读写 localStorage 的 token，client.ts 经此取/存/清。
 */
import type { AuthTokens, User } from "@/api/types";

const K_ACCESS = "rm_access_token";
const K_REFRESH = "rm_refresh_token";
const K_EXPIRES_IN = "rm_access_expires_in";

// 内存态 user（刷新页面丢失，登录后由 /users/me 或登录响应填充）
let user: User | null = null;

function readJson<T>(key: string): T | null {
  const raw = localStorage.getItem(key);
  if (raw === null) return null;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

/** 读取当前令牌对；任一缺失视为未登录。 */
export function getToken(): AuthTokens | null {
  const access = localStorage.getItem(K_ACCESS);
  const refresh = localStorage.getItem(K_REFRESH);
  const expires_in = readJson<number>(K_EXPIRES_IN) ?? 0;
  if (!access || !refresh) return null;
  return { access_token: access, refresh_token: refresh, expires_in };
}

/** 保存新令牌对（登录后 / refresh 轮换后）。 */
export function saveTokens(t: AuthTokens): void {
  localStorage.setItem(K_ACCESS, t.access_token);
  localStorage.setItem(K_REFRESH, t.refresh_token);
  localStorage.setItem(K_EXPIRES_IN, JSON.stringify(t.expires_in));
}

/** 清空令牌与内存 user（登出 / refresh 失败 / 改密踢下线）。 */
export function clearTokens(): void {
  localStorage.removeItem(K_ACCESS);
  localStorage.removeItem(K_REFRESH);
  localStorage.removeItem(K_EXPIRES_IN);
  user = null;
}

export function isLoggedIn(): boolean {
  return getToken() !== null;
}

/** 内存 user 存取。 */
export function setUser(u: User | null): void {
  user = u;
}
export function getUser(): User | null {
  return user;
}

/** 401 / 登出后跳登录并带回跳目标（02 路由：login 支持 ?redirect=）。 */
export function redirectToLogin(target?: string): void {
  clearTokens();
  const from = target ?? `${window.location.pathname}${window.location.search}`;
  window.location.assign(`/login?redirect=${encodeURIComponent(from)}`);
}
