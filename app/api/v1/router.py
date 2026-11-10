"""API v1 聚合路由（07 §6：统一 /api/v1）。"""
from fastapi import APIRouter

api_router = APIRouter()

# T03~T09 各域路由在此挂载：
# from app.api.v1 import auth, products, orders, downloads
# api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
