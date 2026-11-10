# 04 · API 契约（/api/v1）

## 0. 全局约定

- Base：`http://127.0.0.1:8000/api/v1`（dev 前端 proxy 转发，见 08 号）
- 格式：JSON（UTF-8）；文件上传用 `multipart/form-data`
- 鉴权：`Authorization: Bearer <access_token>`（15min）；401 后前端用 refresh_token 调 `/auth/refresh` 换新对（**轮换**：旧 refresh 立即失效）
- 统一错误体：

```json
{ "error": { "code": "ORDER_NOT_PAID", "message": "订单未支付或已失效", "detail": { } } }
```

- 分页：`?page=1&page_size=20`（page_size ≤ 100，默认 20）；响应 `{"items": [...], "total": N, "page": p, "page_size": s}`
- 金额：请求/响应一律**整数分**（`*_cents`）
- 时间：ISO 8601 UTC（`2026-11-09T09:00:00Z`）
- 限流命中统一 `429 RATE_LIMITED`，响应头带 `Retry-After`（秒）

## 1. 错误码表

| HTTP | code | 触发 |
|---|---|---|
| 400 | `BAD_REQUEST` | 参数缺失/格式错 |
| 400 | `FILE_TOO_LARGE` | 上传超限（封面/预览图 ≤ 5MB；样本文件 ≤ 20MB；资源文件 ≤ 2GB；数量限制见各接口） |
| 401 | `UNAUTHENTICATED` | 未带/无效/过期 access token |
| 401 | `REFRESH_INVALID` | refresh token 无效/已轮换 |
| 403 | `FORBIDDEN` | 非管理员访问 /admin API；用户被禁用 |
| 404 | `NOT_FOUND` | 资源不存在（未上架商品对外也返回 404，防探测） |
| 409 | `CONFLICT` | 用户名/邮箱已存在；订单状态非法转移（并发）；重复核销 |
| 409 | `COUPON_INVALID` | 券码不存在/已停用/超量/过期（统一措辞，不暴露明细） |
| 409 | `ALREADY_SUBMITTED` | 订单已提交过「我已付款」 |
| 409 | `HAS_ORDERS` | 删除有订单的商品 |
| 410 | `TOKEN_EXPIRED` | 签名短链过期 |
| 422 | `VALIDATION` | Pydantic 校验失败，`detail` 带字段级错误 |
| 429 | `RATE_LIMITED` | IP 限流（登录 5/min、下单 10/min） |
| 429 | `DOWNLOAD_QUOTA_EXCEEDED` | 订单下载次数超限（7 天 50 次） |

## 2. 健康检查

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | `{"status":"ok","db":"ok","redis":"ok"}`；任一依赖失败 → `503 {"status":"degraded","db":"fail","redis":"ok"}` |

## 3. 认证

| 方法 | 路径 | 鉴权 | 请求 | 响应 200 | 错误 |
|---|---|---|---|---|---|
| POST | `/auth/register` | 无 | `{username?, email?, password(8~64, 至少字母+数字), password_confirm}` | `{user:{id, username, email, is_admin}, tokens:{access_token, refresh_token, expires_in}}` | 409 用户名/邮箱占用；422 校验 |
| POST | `/auth/login` | 无 | `{account(用户名或邮箱), password}` | 同上 | 401 `BAD_CREDENTIALS`（统一措辞，不区分账号/密码错）；403 用户禁用；429 IP 5/min |
| POST | `/auth/refresh` | 无 | `{refresh_token}` | `{access_token, refresh_token(新), expires_in}`；旧 refresh 置 revoked_at | 401 REFRESH_INVALID |
| GET | `/users/me` | 用户 | — | `{id, username, email, is_admin, created_at}` | 401 |
| PUT | `/users/me/password` | 用户 | `{old_password, new_password}` | `{}` | 422 旧密码错/新密码弱 |
| POST | `/auth/logout` | 用户 | `{refresh_token}` | `{}` | 幂等 |

> 密码找回（邮箱）MVP 不做（01 非目标 6）；忘记密码线下联系管理员。

## 4. 商品（前台，只读）

| 方法 | 路径 | 鉴权 | 说明 |
|---|---|---|---|
| GET | `/products` | 无 | query：`category? keyword? sort∈new,price_asc,price_desc(默认new) price_min_cents? price_max_cents?`；**仅 is_listed**；keyword 匹配 title 或 tags 任一含词（SQL：`title ILIKE $1 OR EXISTS(SELECT 1 FROM unnest(tags) t WHERE t ILIKE $1)`） |
| GET | `/products/{id}` | 无 | 404 若不存在或未上架 |
| GET | `/products/{id}/preview` | 无 | 返回 `preview_media` 各媒体项的**签名访问 url**（10 分钟短链，§7），前端不直接拼文件路径 |
| GET | `/categories` | 无 | 固定字典 `[{key,label}]`（tutorial/template/material/ai_asset/other） |
| GET | `/coupons/{code}` | 无 | 券码**有效性预检**（不暴露已用次数/原因明细）：`{valid: bool, type?, value?}` |

**商品响应模型**（列表/详情通用，详情多 `description`）：

```json
{ "id": 1, "title": "…", "subtitle": "…", "category": "tutorial",
  "tags": ["python"], "price_cents": 9900, "original_price_cents": 19900,
  "cover_image": "/uploads/covers/xx.jpg",
  "preview_media": [{"kind":"image","url":"/media/<token>"}],
  "file_name": "pkg.zip", "file_size": 10485760, "is_listed": true,
  "created_at": "2026-11-09T00:00:00Z" }
```

## 5. 订单与下载（前台，需登录，仅本人）

| 方法 | 路径 | 鉴权 | 请求 | 响应/行为 |
|---|---|---|---|---|
| POST | `/orders` | 用户 | `{product_id, coupon_code?}` | **服务端算价**（03 铁律 3）：`201 {order}`，order 含 `order_no, amount_cents, original_cents, discount_cents, pay_status:"pending", expire_at`；错误：404 商品不存在/未上架；409 COUPON_INVALID |
| GET | `/orders` | 用户 | `?status?` | 本人订单分页（created_at 倒序） |
| GET | `/orders/{order_no}` | 用户 | — | 订单详情（**仅本人**，他人订单 404） |
| POST | `/orders/{order_no}/cancel` | 用户 | — | pending→cancelled（条件更新）；非 pending 409 |
| POST | `/orders/{order_no}/paid-submitted` | 用户 | `{note(5~500字)}` | 仅 pending：置 `paid_submitted_at/paid_note`；重复提交 → 409 ALREADY_SUBMITTED（前端刷新状态） |
| GET | `/orders/{order_no}/download` | 用户 | — | 校验链（顺序）：本人且存在 → 404；`pay_status='paid'` → 403 `ORDER_NOT_PAID`；Redis 限流（05 号）超限 → 429 DOWNLOAD_QUOTA_EXCEEDED；**消费前再查一次** pay_status（防核销后撤销窗口）→ 写 download_logs → `302` 到 `/files/{token}` |

**签名短链规则（`GET /files/{token}`，无需登录）**：

- `token = base64url( order_id | exp_epoch | HMAC-SHA256(order_id|exp, SECRET_FILE) )`，`exp = now + 15min`
- 验签失败 → 403 `TOKEN_INVALID`；`exp < now` → 410 TOKEN_EXPIRED；**复核订单 pay_status='paid'** → 403 ORDER_NOT_PAID；否则 `StreamingResponse`（chunk 1MB，`Content-Disposition: attachment; filename*=UTF-8''<urlencoded>`，支持 `Range` 断点续传）
- `downloads/` 目录**不挂载任何静态路由**（06 号红线）

## 6. 后台（需登录 + is_admin，否则 403）

| 方法 | 路径 | 请求 | 响应/行为 |
|---|---|---|---|
| GET | `/admin/products` | `?keyword? listed?` | 全部（含未上架），分页 |
| POST | `/admin/products` | multipart：`title subtitle category tags(逗号串) price_cents original_price_cents? description cover? preview_images?(≤9) preview_files?(≤3,≤20MB) file(≤2GB) listed(bool)` | `201 {product}`；**带 file 才可上架**（否则 422）；封面/预览存 `uploads/`，资源文件存 `downloads/`（服务端二次校验大小/类型，见 06）；审计 `product.create` |
| PUT | `/admin/products/{id}` | 同 POST（缺省=不改；资源文件可换，旧文件物理删除） | `{product}`；审计 `product.update` |
| POST | `/admin/products/{id}/list` | — | 上架（file 缺失 422）；审计 `product.list` |
| POST | `/admin/products/{id}/unlist` | — | 下架；已有订单不受影响；审计 `product.unlist` |
| DELETE | `/admin/products/{id}` | — | 有订单 → 409 HAS_ORDERS（只能下架）；无订单 → 删记录+物理删文件；审计 `product.delete` |
| GET | `/admin/orders` | `?status? submitted(bool) order_no(精确) user(模糊) page` | 全量订单（带用户名/邮箱）；`submitted=true` 即核销工作台队列（按 paid_submitted_at 正序） |
| GET | `/admin/orders/{order_no}` | — | 详情 + `download_logs` 列表 |
| POST | `/admin/orders/{order_no}/confirm` | `{pay_channel:"wechat"|"alipay", note?}` | 条件更新 pending→paid（03 铁律 1），rowcount=0 → 409；审计 `order.confirm`（reason=note） |
| POST | `/admin/orders/{order_no}/revoke` | `{reason(≥5字必填)}` | paid→revoked；审计 `order.revoke` |
| GET | `/admin/coupons` | `?active?` | 券列表 |
| GET | `/admin/coupons/{code}/usages` | — | `[{order_no, username, discount_cents, used_at}]` |
| POST | `/admin/coupons` | `{type:"fixed"|"percent", value, max_uses(≥1), valid_from, valid_to, count(1~100)}` | 批量生成 `201 {codes:[...]}`；percent 值 1~95；审计 `coupon.create` |
| POST | `/admin/coupons/{code}/disable` | — | is_active=false（已用部分不受影响）；审计 `coupon.disable` |
| GET | `/admin/users` | `?keyword?` | 用户列表 + 各自订单数 |
| POST | `/admin/users/{id}/toggle` | — | is_active 翻转；**禁禁用自己/最后一个管理员**（409）；审计 `user.toggle` |
| GET | `/admin/audit` | `?action? from? to?` | 审计日志分页倒序 |
| GET | `/admin/stats` | — | 概览卡片：`{today_orders, pending_review, listed_products, week_gmv_cents}` |

## 7. 预览媒体短链（`GET /media/{token}`，无需登录）

- 规则同 §5 签名短链，绑定 **product_id + media 相对路径**，`exp = 10min`
- 仅允许 `uploads/covers/`、`uploads/preview/` 前缀路径，防目录穿越
- 图片直接返回（带 `Cache-Control: private, max-age=600`），文件类同 `/files` 处理

## 8. 管理端种子

- `alembic upgrade head` 后：`python -m app.seed_admin --username admin --email admin@local --password <从 stdin 读取>`（幂等：已存在 → 409 提示）
- is_admin 仅由 seed / 后台 toggle 产生，**注册接口不可提权**
