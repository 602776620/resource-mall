"""FastAPI 入口：create_app + 全局 handler + 健康检查（08 §7）。"""
import logging

from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.deps import get_redis
from app.core.exceptions import register_exception_handlers
from app.db.base import SessionLocal

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("app")


def create_app() -> FastAPI:
    app = FastAPI(title="resource-mall", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_exception_handlers(app)
    app.include_router(api_router, prefix="/api/v1")

    @app.get("/health", tags=["infra"])
    def health() -> dict:
        """DB/Redis 双探活：任一失败 → 503 degraded（08 §7）。"""
        db_status, redis_status = "ok", "ok"
        try:
            db = SessionLocal()
            try:
                db.execute(text("SELECT 1"))
            finally:
                db.close()
        except Exception as e:  # noqa: BLE001 - 探活需吞异常转状态
            logger.warning("health: db probe failed: %s", e)
            db_status = "fail"
        try:
            get_redis().ping()
        except Exception as e:  # noqa: BLE001
            logger.warning("health: redis probe failed: %s", e)
            redis_status = "fail"

        ok = db_status == "ok" and redis_status == "ok"
        body = {"status": "ok" if ok else "degraded", "db": db_status, "redis": redis_status}
        if not ok:
            return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=body)
        return body

    return app


app = create_app()
