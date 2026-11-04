import zipfile
from functools import partial
from html import escape
from io import BytesIO

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from openpyxl.utils.exceptions import InvalidFileException
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.callbacks import AdminCb, AgentCb
from app.bot.filters import RoleFilter
from app.bot.keyboards import staff as kb
from app.bot.middlewares import AfterCommit
from app.bot.states import StaffStates
from app.bot.utils import callback_message, safe_edit
from app.modules.agents.service import AgentService
from app.modules.excel_sync.service import ExcelSyncService
from app.modules.properties.workflows import dispatch_status_side_effects
from app.modules.users.models import User
from app.modules.users.service import UserService
from app.shared.i18n import Translator
from app.shared.security import UserRole
from app.shared.timeutils import utcnow

# Everything in this router is owner-only
router = Router(name="staff.owner")
router.message.filter(RoleFilter(UserRole.OWNER))
router.callback_query.filter(RoleFilter(UserRole.OWNER))

MAX_EXCEL_BYTES = 10 * 1024 * 1024


# ------------------------------------------------------------------ Excel
@router.callback_query(AdminCb.filter(F.section == "excel_export"))
async def excel_export(callback: CallbackQuery, session: AsyncSession, t: Translator) -> None:
    content = await ExcelSyncService(session).export_bytes()
    await callback.answer()
    if message := callback_message(callback):
        filename = f"domik_properties_{utcnow():%Y%m%d_%H%M}.xlsx"
        await message.answer_document(
            BufferedInputFile(content, filename=filename), caption=t("admin.excel_exported")
        )


@router.callback_query(AdminCb.filter(F.section == "excel_import"))
async def excel_import_prompt(callback: CallbackQuery, state: FSMContext, t: Translator) -> None:
    await state.set_state(StaffStates.excel_upload)
    await callback.answer()
    if message := callback_message(callback):
        await message.answer(t("admin.excel_send_file"))


@router.message(StaffStates.excel_upload, F.document)
async def excel_import(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    t: Translator,
    bot: Bot,
    after_commit: AfterCommit,
) -> None:
    document = message.document
    if document is None or not (document.file_name or "").lower().endswith(".xlsx"):
        await message.answer(t("admin.excel_bad_file"))
        return
    if document.file_size and document.file_size > MAX_EXCEL_BYTES:
        await message.answer(t("admin.excel_too_big"))
        return
    await state.clear()

    buffer = BytesIO()
    await bot.download(document, destination=buffer)
    buffer.seek(0)
    try:
        report = await ExcelSyncService(session).import_file(buffer, f"telegram:{user.telegram_id}")
    except (InvalidFileException, zipfile.BadZipFile, KeyError, StopIteration):
        await message.answer(t("admin.excel_bad_file"))
        return

    for result in report.status_changes:
        after_commit.append(partial(dispatch_status_side_effects, result))
    text = t(
        "admin.excel_report",
        created=report.created,
        updated=report.updated,
        unchanged=report.unchanged,
        conflicts=len(report.conflicts),
        errors=len(report.errors),
    )
    if report.conflicts:
        text += "\n\n" + t("admin.excel_conflicts") + "\n" + escape(", ".join(report.conflicts[:30]))
    if report.errors:
        text += "\n\n" + escape("\n".join(report.errors[:15]))
    await message.answer(text)


# ------------------------------------------------------------------ agents
async def _agents_text(session: AsyncSession, t: Translator) -> tuple[str, list]:
    agents = list(await AgentService(session).list_all())
    lines = [
        f"{'🟢' if a.is_active else '⚪'} {escape(a.display_name)} — {escape(a.user.mention)}" for a in agents
    ]
    text = t("admin.agents_title") + "\n\n" + ("\n".join(lines) or "—") + "\n\n" + t("admin.agents_hint")
    return text, agents


@router.callback_query(AdminCb.filter(F.section == "agents"))
async def list_agents(callback: CallbackQuery, session: AsyncSession, t: Translator) -> None:
    text, agents = await _agents_text(session, t)
    await safe_edit(callback, text, kb.agents_list(agents, t))
    await callback.answer()


@router.callback_query(AgentCb.filter(F.action == "off"))
async def deactivate_agent(
    callback: CallbackQuery, callback_data: AgentCb, session: AsyncSession, t: Translator
) -> None:
    await AgentService(session).deactivate(callback_data.id)
    text, agents = await _agents_text(session, t)
    await safe_edit(callback, text, kb.agents_list(agents, t))
    await callback.answer(t("admin.saved"))


@router.message(Command("add_agent"))
async def add_agent(message: Message, command: CommandObject, session: AsyncSession, t: Translator) -> None:
    """/add_agent <telegram_id> [display name] — the user must have pressed /start before."""
    args = (command.args or "").split(maxsplit=1)
    if not args or not args[0].lstrip("-").isdigit():
        await message.answer(t("admin.add_agent_usage"))
        return
    target = await UserService(session).get_by_telegram_id(int(args[0]))
    if target is None:
        await message.answer(t("admin.user_not_found"))
        return
    agent = await AgentService(session).register(target, args[1] if len(args) > 1 else None)
    await message.answer(t("admin.agent_added", name=escape(agent.display_name)))
