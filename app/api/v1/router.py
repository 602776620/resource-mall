"""API v1 聚合路由（07 §6：统一 /api/v1）。"""
from fastapi import APIRouter

from app.api.v1 import auth, coupons, files, orders, products, users

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
# T04：商品（前台 /products、/categories、/media + 后台 /admin/*）
api_router.include_router(products.router)
api_router.include_router(products.admin_router, prefix="/admin", tags=["admin"])
# T06：订单（用户 /orders + 后台 /admin/orders 核销）+ 券预检 /coupons/{code}
api_router.include_router(orders.router, prefix="/orders", tags=["orders"])
api_router.include_router(orders.admin_router, prefix="/admin/orders", tags=["admin-orders"])
api_router.include_router(coupons.router, tags=["coupons"])
# T07：资源文件签名短链 /files/{token}（无鉴权，验签+消费前复核 paid；04 §5 / 06 红线）
api_router.include_router(files.router)
