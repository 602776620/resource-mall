/**
 * 认证域请求函数（04 §3）。统一经 client.http（带 401 刷新）。
 * 注意：login/refresh 成功响应即返回 user + tokens，页面据此落地 auth store。
 */
import { http } from "@/api/client";
import type { LoginResponse, User } from "@/api/types";
import * as auth from "@/stores/auth";

export interface LoginPayload {
  account: string; // 用户名或邮箱
  password: string;
}

export interface RegisterPayload {
  username?: string;
  email?: string;
  password: string;
  password_confirm: string;
}

/** 登录（04 §3）。成功返回 user + tokens。 */
export async function login(p: LoginPayload): Promise<LoginResponse> {
  const { data } = await http.post<LoginResponse>("/auth/login", p);
  auth.saveTokens(data.tokens);
  auth.setUser(data.user);
  return data;
}

/** 注册（04 §3）。409 占用 / 422 校验失败。 */
export async function register(p: RegisterPayload): Promise<LoginResponse> {
  const { data } = await http.post<LoginResponse>("/auth/register", p);
  auth.saveTokens(data.tokens);
  auth.setUser(data.user);
  return data;
}

/** 拉取当前用户（04 §3 /users/me）。401 由拦截器刷新重试；仍失败则跳登录。 */
export async function fetchMe(): Promise<User> {
  const { data } = await http.get<User>("/users/me");
  auth.setUser(data);
  return data;
}

/** 修改密码（04 §3）。成功后服务端使旧 token 全失效 → 前端跳登录。 */
export async function changePassword(p: {
  old_password: string;
  new_password: string;
}): Promise<void> {
  await http.put("/users/me/password", p);
}
