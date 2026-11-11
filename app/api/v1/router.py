"""API v1 聚合路由（07 §6：统一 /api/v1）。"""
from fastapi import APIRouter

from app.api.v1 import auth, coupons, orders, products, users

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
