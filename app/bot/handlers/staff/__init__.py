from aiogram import Router

from app.bot.filters import RoleFilter
from app.bot.handlers.staff import menu, owner, properties, schedule, tickets
from app.shared.security import STAFF_ROLES


def build_staff_router() -> Router:
    router = Router(name="staff")
    # Role check once for the whole subtree: clients never reach staff handlers
    router.message.filter(RoleFilter(*STAFF_ROLES))
    router.callback_query.filter(RoleFilter(*STAFF_ROLES))
    router.include_routers(menu.router, owner.router, properties.router, schedule.router, tickets.router)
    return router
