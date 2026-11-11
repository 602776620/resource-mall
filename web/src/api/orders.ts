/**
 * 订单域请求函数（04 §5 用户 / §6 管理员核销）。统一经 client.http。
 * 金额以「分」存；分↔元换算由 lib/money 负责（07 §4 红线 2）。
 */
import { http, getErrorMessage } from "@/api/client";
import type { Paginated } from "@/api/types";

export type PayStatus = "pending" | "paid" | "revoked" | "cancelled";

/** 订单（04 §5 响应模型；管理端多 user_id/username/email）。 */
export interface Order {
  order_no: string;
  product_id: number;
  product_title: string;
  amount_cents: number;
  original_cents: number;
  coupon_code: string | null;
  discount_cents: number;
  pay_status: PayStatus;
  pay_channel: "wechat" | "alipay" | null;
  paid_submitted_at: string | null;
  paid_note: string | null;
  paid_at: string | null;
  expire_at: string;
  created_at: string;
}

/** 订单详情（多文件/撤销字段）。 */
export interface OrderDetail extends Order {
  file_name: string | null;
  file_size: number | null;
  revoked_at: string | null;
  revoke_reason: string | null;
}

/** 管理端订单（多用户信息）。 */
export interface AdminOrder extends Order {
  user_id: number;
  username: string | null;
  email: string | null;
}

export interface AdminOrderDetail extends AdminOrder {
  file_name: string | null;
  file_size: number | null;
  download_logs: { ip: string | null; user_agent: string | null; created_at: string }[];
}

export interface ListOrdersParams {
  status?: PayStatus;
  page?: number;
  page_size?: number;
}

export interface AdminOrdersParams {
  status?: PayStatus;
  submitted?: boolean;
  order_no?: string;
  user?: string;
  page?: number;
  page_size?: number;
}

export interface CouponCheck {
  valid: boolean;
  type?: "fixed" | "percent";
  value?: number;
}

/** 券码有效性预检（04 §4）。只回 valid + 类型/值，不暴露已用/原因明细。 */
export function checkCoupon(code: string): Promise<CouponCheck> {
  return http.get<CouponCheck>(`/coupons/${encodeURIComponent(code.trim())}`).then((r) => r.data);
}

/** 下单（服务端算价，03 铁律 3）。201。 */
export function createOrder(product_id: number, coupon_code?: string): Promise<Order> {
  return http
    .post<Order>("/orders", { product_id, coupon_code: coupon_code || null })
    .then((r) => r.data);
}

/** 我的订单（created_at 倒序）。 */
export function listOrders(params: ListOrdersParams = {}): Promise<Paginated<Order>> {
  return http.get<Paginated<Order>>("/orders", { params }).then((r) => r.data);
}

/** 订单详情（仅本人，他人 404）。 */
export function getOrder(orderNo: string): Promise<OrderDetail> {
  return http.get<OrderDetail>(`/orders/${orderNo}`).then((r) => r.data);
}

/** 取消（pending→cancelled）。 */
export function cancelOrder(orderNo: string): Promise<Order> {
  return http.post<Order>(`/orders/${orderNo}/cancel`).then((r) => r.data);
}

/** 我已付款（提交支付说明，进入核销队列）。note ≥5 字。 */
export function submitPaid(orderNo: string, note: string): Promise<Order> {
  return http.post<Order>(`/orders/${orderNo}/paid-submitted`, { note }).then((r) => r.data);
}

// ---- 管理端（04 §6，核销工作台）----

export function listAdminOrders(params: AdminOrdersParams = {}): Promise<Paginated<AdminOrder>> {
  return http.get<Paginated<AdminOrder>>("/admin/orders", { params }).then((r) => r.data);
}

export function getAdminOrder(orderNo: string): Promise<AdminOrderDetail> {
  return http.get<AdminOrderDetail>(`/admin/orders/${orderNo}`).then((r) => r.data);
}

/** 核销（pending→paid 条件更新）。并发/已取消 → 409。 */
export function confirmOrder(
  orderNo: string,
  pay_channel: "wechat" | "alipay",
  note?: string,
): Promise<Order> {
  return http
    .post<Order>(`/admin/orders/${orderNo}/confirm`, { pay_channel, note: note || null })
    .then((r) => r.data);
}

/** 撤销（paid→revoked）。reason ≥5 字必填。 */
export function revokeOrder(orderNo: string, reason: string): Promise<Order> {
  return http.post<Order>(`/admin/orders/${orderNo}/revoke`, { reason }).then((r) => r.data);
}

export { getErrorMessage };
