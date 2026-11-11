/**
 * 商品域请求函数（04 §4 前台，只读，无鉴权）。统一经 client.http。
 * 金额分↔元、media 短链拼前缀等展示逻辑由页面/lib 处理（07 §4 红线 2）。
 */
import { http } from "@/api/client";
import type { Paginated } from "@/api/types";

/** 商品媒体项（04 §4 响应模型 preview_media 元素）。 */
export interface MediaItem {
  kind: "image" | "file";
  url: string; // 前台为签名短链 /media/<token>
  name?: string | null;
}

/** 商品（列表/详情通用，详情多 description）。 */
export interface Product {
  id: number;
  title: string;
  subtitle: string | null;
  category: string;
  tags: string[];
  price_cents: number;
  original_price_cents: number | null;
  cover_image: string | null; // 前台为签名短链
  preview_media: MediaItem[];
  file_name: string | null;
  file_size: number | null;
  is_listed: boolean;
  created_at: string;
  description?: string | null; // 详情
}

/** 分类字典（04 §4 /categories）。 */
export interface Category {
  key: string;
  label: string;
}

export interface ListProductsParams {
  category?: string;
  keyword?: string;
  sort?: "new" | "price_asc" | "price_desc";
  price_min_cents?: number;
  price_max_cents?: number;
  page?: number;
  page_size?: number;
}

/** 商品列表（04 §4，仅上架）。 */
export function listProducts(params: ListProductsParams = {}): Promise<Paginated<Product>> {
  return http.get<Paginated<Product>>("/products", { params }).then((r) => r.data);
}

/** 商品详情（04 §4）。未上架/不存在 → 404。 */
export function getProduct(id: number | string): Promise<Product> {
  return http.get<Product>(`/products/${id}`).then((r) => r.data);
}

/** 预览媒体签名短链（04 §4/§7）。 */
export function getPreview(id: number | string): Promise<{ items: MediaItem[] }> {
  return http.get<{ items: MediaItem[] }>(`/products/${id}/preview`).then((r) => r.data);
}

/** 分类字典（04 §4）。 */
export function getCategories(): Promise<Category[]> {
  return http.get<Category[]>("/categories").then((r) => r.data);
}

/**
 * 签名短链 → 浏览器可访问的完整 URL（/media/{token} → /api/v1/media/{token}）。
 * 后端 /media 路由挂在 /api/v1 下（main.py 统一前缀 /api/v1 + products.router 的 /media），
 * dev proxy 只转发 /api 前缀，故浏览器侧需补全 /api/v1。
 */
export function mediaUrl(signed: string | null | undefined): string {
  if (!signed) return "";
  return signed.startsWith("/api/v1/") ? signed : `/api/v1${signed}`;
}
