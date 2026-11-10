/**
 * 与后端对齐的公共响应类型（04 §0 统一错误体 + 认证契约 04 §3）。
 * 字段只增不改语义（07 §6）。
 */

/** 统一错误体：{ "error": { code, message, detail? } } */
export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    detail?: unknown;
  };
}

/** 用户（04 §3 /users/me 及 register/login 返回的 user） */
export interface User {
  id: number;
  username: string;
  email: string;
  is_admin: boolean;
  created_at?: string;
}

/** 令牌对（04 §3）。expires_in 为 access 剩余秒数。 */
export interface AuthTokens {
  access_token: string;
  refresh_token: string;
  expires_in: number;
}

/** login/register 响应 */
export interface LoginResponse {
  user: User;
  tokens: AuthTokens;
}

/** 通用分页包装（列表接口，04 §4） */
export interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}
