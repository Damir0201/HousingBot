from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any

from aiogram.types import Update
from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.bot.main import create_dispatcher, set_commands
from app.config import get_settings
from app.infrastructure.database.session import get_engine
from app.infrastructure.llm.client import build_llm_client
from app.infrastructure.redis.client import get_redis
from app.infrastructure.telegram.bot import create_bot
from app.shared.exceptions import DomikError, PermissionDeniedError
from app.shared.logging import get_logger, setup_logging
from app.shared.security import secure_compare

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_logging()
    settings = get_settings()
    app.state.bot = None
    app.state.dp = None
    app.state.llm = None

    if settings.bot_mode == "webhook":
        bot = create_bot()
        llm = build_llm_client()
        dp = create_dispatcher(llm=llm)
        app.state.bot = bot
        app.state.dp = dp
        app.state.llm = llm
        await set_commands(bot)
        if settings.webhook_url:
            await bot.set_webhook(
                url=settings.webhook_url,
                secret_token=settings.webhook_secret.get_secret_value(),
                allowed_updates=dp.resolve_used_update_types(),
                drop_pending_updates=False,
            )
            log.info("webhook.registered", url=settings.webhook_url)

    try:
        yield
    finally:
        if app.state.llm is not None and hasattr(app.state.llm, "aclose"):
            await app.state.llm.aclose()
        if app.state.dp is not None:
            await app.state.dp.storage.close()
        if app.state.bot is not None:
            await app.state.bot.session.close()
        await get_redis().aclose()
        await get_engine().dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )

    @app.exception_handler(DomikError)
    async def handle_domik_error(_request: Request, exc: DomikError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.http_status,
            content={
                "error": exc.__class__.__name__,
                "i18n_key": exc.i18n_key,
                "message": str(exc),
                "context": exc.context,
            },
        )

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": settings.app_name}

    @app.post(settings.webhook_path, tags=["telegram"], include_in_schema=False)
    async def telegram_webhook(
        request: Request,
        secret: Annotated[str | None, Header(alias="X-Telegram-Bot-Api-Secret-Token")] = None,
    ) -> dict[str, Any]:
        if not secure_compare(secret, settings.webhook_secret.get_secret_value()):
            raise PermissionDeniedError("Invalid webhook secret token")
        if request.app.state.dp is None or request.app.state.bot is None:
            return {"ok": False, "detail": "bot_mode is not webhook"}
        payload = await request.json()
        update = Update.model_validate(payload, context={"bot": request.app.state.bot})
        await request.app.state.dp.feed_update(request.app.state.bot, update)
        return {"ok": True}

    app.include_router(api_router)
    return app


app = create_app()
