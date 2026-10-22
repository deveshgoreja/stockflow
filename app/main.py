from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.api import inventory, orders, products, reports
from app.core.config import settings
from app.core.errors import error_response, register_error_handlers
from app.database.connection import SessionDep
from app.schemas.common import HealthRead


def create_app() -> FastAPI:
    app = FastAPI(
        title="StockFlow API",
        version="1.0.0",
        description=(
            "Inventory and order management with transactional, concurrency-safe stock control."
        ),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(app)
    for module in (products, inventory, orders, reports):
        app.include_router(module.router)

    @app.get("/health", response_model=HealthRead, tags=["health"])
    def health(session: SessionDep) -> HealthRead | JSONResponse:
        try:
            session.execute(text("SELECT 1"))
        except OperationalError:
            return error_response(503, "DATABASE_UNAVAILABLE", "Database is not reachable")
        return HealthRead(status="ok", database="ok")

    return app


app = create_app()
