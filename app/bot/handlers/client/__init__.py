from aiogram import Router

from app.bot.handlers.client import assistant, booking, search, start


def build_client_router() -> Router:
    router = Router(name="client")
    # order matters: the AI catch-all (assistant) must be the last one
    router.include_routers(start.router, search.router, booking.router, assistant.router)
    return router
