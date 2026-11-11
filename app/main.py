"""FastAPI 入口：create_app + 全局 handler + 健康检查（08 §7）+ 后台任务（05 §7）。"""
import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

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


async def _order_expiry_loop() -> None:
    """订单超时取消任务（05 §7）：每 60s 扫描 pending 且过期 → cancelled（含券回滚）。幂等、单实例。

    DB 操作为同步，放到线程池避免阻塞事件循环；异常吞掉记日志（任务不能崩）。
    """
    from app.services import order_service

    while True:
        await asyncio.sleep(60)  # 05 §7：固定 60s 周期

        def _run() -> None:
            db = SessionLocal()
            try:
                n = order_service.expire_pending_orders(db)
                if n:
                    logger.info("order-expiry: cancelled %d expired order(s)", n)
            except Exception as e:  # noqa: BLE001 - 后台任务需自吞
                logger.error("order-expiry task failed: %s", e)
            finally:
                db.close()

        await asyncio.to_thread(_run)


@asynccontextmanager
async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
    task = asyncio.create_task(_order_expiry_loop())
    logger.info("background task started: order-expiry (60s)")
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


def create_app() -> FastAPI:
    app = FastAPI(title="resource-mall", version="0.1.0", lifespan=_lifespan)

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
