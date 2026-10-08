from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.agent.routes import router as agent_router
from app.api.auth.routes import router as auth_router
from app.api.cart.routes import router as cart_router
from app.api.orders.routes import router as orders_router
from app.api.products.routes import router as products_router
from app.api.seller.routes import router as seller_router
from app.core.config import get_settings
from app.core.errors import register_error_handlers


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Shop + AI Agent (learning project)", version="1.0.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.FRONTEND_URL],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(app)

    api = APIRouter(prefix="/api")
    for r in (auth_router, products_router, cart_router, orders_router, seller_router, agent_router):
        api.include_router(r)
    app.include_router(api)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/uploads", StaticFiles(directory=upload_dir), name="uploads")
    return app


app = create_app()
