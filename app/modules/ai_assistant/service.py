import json
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.infrastructure.llm.client import LLMClient
from app.infrastructure.llm.schemas import ChatMessage
from app.modules.ai_assistant.memory import ConversationMemory
from app.modules.ai_assistant.prompts import build_system_prompt
from app.modules.ai_assistant.tools import ToolContext, ToolRegistry, default_registry
from app.modules.crm.service import LeadService
from app.modules.users.models import User
from app.shared.exceptions import ExternalServiceError
from app.shared.i18n import Language
from app.shared.logging import get_logger
from app.shared.timeutils import utcnow

log = get_logger(__name__)


@dataclass
class AssistantReply:
    text: str | None
    property_ids: list[int] = field(default_factory=list)
    ticket_id: int | None = None
    fallback: bool = False  # LLM unavailable -> bot shows scripted menu


class AssistantService:
    def __init__(
        self,
        session: AsyncSession,
        llm: LLMClient | None,
        memory: ConversationMemory,
        registry: ToolRegistry | None = None,
    ) -> None:
        self.session = session
        self.llm = llm
        self.memory = memory
        self.registry = registry or default_registry()
        self.settings = get_settings()

    async def reply(self, user: User, text: str) -> AssistantReply:
        if self.llm is None:
            return AssistantReply(text=None, fallback=True)

        language = user.language or Language(self.settings.default_language)
        lead = await LeadService(self.session).get_or_create(user)
        history = await self.memory.load(user.id)

        system = ChatMessage(
            role="system",
            content=build_system_prompt(
                language=language,
                today=utcnow().astimezone(self.settings.tz).strftime("%Y-%m-%d (%A)"),
                timezone=self.settings.timezone,
                preferences=json.dumps(lead.criteria, ensure_ascii=False) if lead.criteria else "",
            ),
        )
        ctx = ToolContext(
            session=self.session,
            user=user,
            language=language,
            transcript=[
                f"{m.role}: {m.content}" for m in history if m.role in ("user", "assistant") and m.content
            ]
            + [f"user: {text}"],
        )
        new_messages: list[ChatMessage] = [ChatMessage(role="user", content=text)]

        try:
            response: ChatMessage | None = None
            for _ in range(self.settings.llm_max_tool_iterations):
                response = await self.llm.chat([system, *history, *new_messages], self.registry.definitions)
                new_messages.append(response)
                if not response.tool_calls:
                    break
                for call in response.tool_calls:
                    result = await self.registry.execute(call, ctx)
                    new_messages.append(ChatMessage(role="tool", tool_call_id=call.id, content=result))
            if response is None or response.tool_calls:
                # iteration limit hit: close the turn so memory stays consistent
                response = ChatMessage(role="assistant", content=None)
                new_messages.append(response)
        except ExternalServiceError:
            log.warning("ai.llm_unavailable", user_id=user.id)
            return AssistantReply(
                text=None, property_ids=ctx.property_ids, ticket_id=ctx.ticket_id, fallback=True
            )

        await self.memory.append(user.id, *new_messages)
        return AssistantReply(
            text=response.content,
            property_ids=ctx.property_ids[:5],
            ticket_id=ctx.ticket_id,
            fallback=not response.content,
        )

    async def reset(self, user: User) -> None:
        await self.memory.clear(user.id)
