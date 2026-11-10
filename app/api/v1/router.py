"""API v1 聚合路由（07 §6：统一 /api/v1）。"""
from fastapi import APIRouter

from app.api.v1 import auth, products, users

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
# T04：商品（前台 /products、/categories、/media + 后台 /admin/*）
api_router.include_router(products.router)
api_router.include_router(products.admin_router, prefix="/admin", tags=["admin"])

# T06~T08 各域路由在此挂载：
# from app.api.v1 import orders, coupons
# api_router.include_router(orders.router, prefix="/orders", tags=["orders"])
