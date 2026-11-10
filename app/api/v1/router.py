"""API v1 聚合路由（07 §6：统一 /api/v1）。"""
from fastapi import APIRouter

from app.api.v1 import auth, users

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])

# T04~T08 各域路由在此挂载：
# from app.api.v1 import products, orders, downloads
# api_router.include_router(products.router, prefix="/products", tags=["products"])
