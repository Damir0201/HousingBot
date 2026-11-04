from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.callbacks import AdminCb
from app.bot.filters import RoleFilter, TextKey
from app.bot.keyboards import staff as kb
from app.bot.utils import safe_edit
from app.modules.crm.schemas import DashboardStats
from app.modules.crm.service import StatsService
from app.modules.users.models import User
from app.shared.i18n import Translator
from app.shared.security import UserRole

router = Router(name="staff.menu")


@router.message(Command("admin"))
@router.message(TextKey("menu.admin"))
async def admin_menu(message: Message, state: FSMContext, user: User, t: Translator) -> None:
    await state.clear()
    await message.answer(t("admin.title"), reply_markup=kb.admin_menu(t, user.role == UserRole.OWNER))


@router.callback_query(AdminCb.filter(F.section == "menu"))
async def admin_menu_cb(callback: CallbackQuery, state: FSMContext, user: User, t: Translator) -> None:
    await state.clear()
    await safe_edit(callback, t("admin.title"), kb.admin_menu(t, user.role == UserRole.OWNER))
    await callback.answer()


def format_stats(stats: DashboardStats, t: Translator) -> str:
    def block(title: str, data: dict[str, int], prefix: str) -> str:
        lines = [f"  • {t(f'{prefix}.{key}')}: <b>{value}</b>" for key, value in sorted(data.items())]
        return f"<b>{title}</b>\n" + ("\n".join(lines) if lines else "  —")

    agents = (
        "\n".join(
            f"  • {a.name}: ✅ {a.bookings.get('completed', 0)} · 📅 {a.bookings.get('scheduled', 0)}"
            f" · ❌ {a.bookings.get('cancelled', 0)} · 🚫 {a.bookings.get('no_show', 0)}"
            for a in stats.agents
        )
        or "  —"
    )
    return "\n\n".join(
        [
            t("admin.stats_title", days=(stats.period_to - stats.period_from).days),
            block(t("admin.stats_properties"), stats.properties_by_status, "property.status"),
            block(t("admin.stats_bookings"), stats.bookings_by_status, "booking.status"),
            f"<b>{t('admin.stats_agents')}</b>\n{agents}",
            block(t("admin.stats_tickets"), stats.tickets_by_status, "ticket.status"),
            block(t("admin.stats_leads"), stats.leads_by_status, "lead.status"),
            t("admin.stats_footer", clients=stats.new_clients, waitlist=stats.waitlist_size),
        ]
    )


@router.callback_query(AdminCb.filter(F.section == "stats"), RoleFilter(UserRole.OWNER))
async def stats(callback: CallbackQuery, session: AsyncSession, t: Translator) -> None:
    data = await StatsService(session).dashboard(days=30)
    await safe_edit(callback, format_stats(data, t), kb.back_markup(t))
    await callback.answer()
