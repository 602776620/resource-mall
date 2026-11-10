/**
 * 统一 axios 实例 + 401 刷新拦截器（07 §4 红线 4：所有请求经此；04 §0/§3）。
 *
 * 刷新语义（04 §3，轮换）：
 *  - 收到 401 且带可刷新令牌 → 调 /auth/refresh 换新对（旧 refresh 立即失效）。
 *  - 刷新成功 → 原请求「重试一次」（带新 access token）。
 *  - 并发多个 401 共享同一次刷新（single-flight），避免旧 refresh 被并发复用导致 401。
 *  - 刷新失败（REFRESH_INVALID / 网络）→ 清除本地态并跳登录（改密踢下线 / 过期）。
 *  - 原请求重试后若仍 401（retried 标记）→ 直接跳登录，不再刷新，防死循环。
 */
import axios, {
  AxiosError,
  type AxiosInstance,
  type InternalAxiosRequestConfig,
} from "axios";
import * as auth from "@/stores/auth";
import type { ApiErrorBody } from "@/api/types";

/** 重试标记：该请求已因 401 重放过一次。 */
declare module "axios" {
  export interface InternalAxiosRequestConfig {
    retried?: boolean;
  }
}

const baseURL = "/api/v1";

export const http: AxiosInstance = axios.create({ baseURL });

// 请求前注入最新 access token（重放时取到的是刷新后的新值）。
http.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const t = auth.getToken();
  if (t) config.headers.Authorization = `Bearer ${t.access_token}`;
  return config;
});

let refreshInFlight: Promise<boolean> | null = null;

/** 裸 axios 调 refresh：不挂 Authorization、不经过下方拦截器，规避递归。 */
function rawRefresh(refreshToken: string): Promise<boolean> {
  return axios
    .post(`${baseURL}/auth/refresh`, { refresh_token: refreshToken })
    .then((res) => {
      const body = res.data as { access_token: string; refresh_token: string; expires_in: number };
      auth.saveTokens(body);
      return true;
    })
    .catch(() => false);
}

function doRefresh(): Promise<boolean> {
  if (!refreshInFlight) {
    const t = auth.getToken();
    if (!t) return Promise.resolve(false);
    refreshInFlight = rawRefresh(t.refresh_token).finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

function isApiError(v: unknown): v is ApiErrorBody {
  return typeof v === "object" && v !== null && "error" in v;
}

/** 从错误对象提取错误码（无则回退 HTTP 状态）。 */
export function getErrorCode(err: unknown): string {
  if (err instanceof AxiosError) {
    if (err.response?.data && isApiError(err.response.data)) return err.response.data.error.code;
    return String(err.response?.status ?? "NETWORK_ERROR");
  }
  return "UNKNOWN";
}

/** 从错误对象提取人可读 message（后端错误体优先，回退 axios message）。 */
export function getErrorMessage(err: unknown, fallback = "请求失败"): string {
  if (err instanceof AxiosError) {
    if (err.response?.data && isApiError(err.response.data)) return err.response.data.error.message;
    return err.message || fallback;
  }
  return fallback;
}

http.interceptors.response.use(
  (res) => res,
  async (error: AxiosError<ApiErrorBody>) => {
    const config = error.config as (InternalAxiosRequestConfig & { retried?: boolean }) | undefined;
    const isRefreshCall = config?.url === "/auth/refresh";

    if (error.response?.status === 401 && config && !isRefreshCall && !config.retried) {
      const ok = await doRefresh();
      if (ok) {
        config.retried = true; // 只重试一次
        return http.request(config); // 请求拦截器会注入新 access token
      }
      // 刷新失败：本地曾持有 refresh 才跳登录（避免匿名 401 误跳）
      if (auth.isLoggedIn()) auth.redirectToLogin();
    }
    return Promise.reject(error);
  },
);

/** 登出（尽力吊销 refresh，失败也清本地并跳登录，04 §3 logout 幂等）。 */
export async function logout(): Promise<void> {
  const t = auth.getToken();
  if (t) {
    try {
      await axios.post(`${baseURL}/auth/logout`, { refresh_token: t.refresh_token });
    } catch {
      /* 忽略：本地清理为准 */
    }
  }
  auth.redirectToLogin();
}
