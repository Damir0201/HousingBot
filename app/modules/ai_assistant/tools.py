import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.llm.schemas import ToolCall, ToolDefinition
from app.modules.ai_assistant.faq import FaqService
from app.modules.crm.models import TicketCategory, TicketPriority
from app.modules.crm.schemas import TicketCreate
from app.modules.crm.service import LeadService, TicketService
from app.modules.properties.schemas import PropertyBrief, PropertySearchCriteria
from app.modules.properties.service import PropertyService
from app.modules.users.models import User
from app.shared.exceptions import DomikError
from app.shared.i18n import Language
from app.shared.logging import get_logger

log = get_logger(__name__)


@dataclass
class ToolContext:
    session: AsyncSession
    user: User
    language: Language
    transcript: list[str] = field(default_factory=list)
    # side-channel results used by the bot to render cards / notify operators
    property_ids: list[int] = field(default_factory=list)
    ticket_id: int | None = None


# ----------------------------------------------------------------- arguments
class PropertyIdArgs(BaseModel):
    property_id: int = Field(..., description="Property id returned by search_properties")


class FaqArgs(BaseModel):
    query: str = Field(..., description="The client's question, rephrased as a short search query")


class HandoffArgs(BaseModel):
    category: TicketCategory = Field(..., description="Topic of the request")
    priority: TicketPriority = Field(TicketPriority.NORMAL, description="high = urgent / angry client")
    summary: str = Field(
        ..., description="Complete summary for the operator: what the client wants, details, what was tried"
    )


# ----------------------------------------------------------------- handlers
async def _search_properties(args: PropertySearchCriteria, ctx: ToolContext) -> Any:
    props = await PropertyService(ctx.session).search(args)
    ctx.property_ids.extend(p.id for p in props if p.id not in ctx.property_ids)
    return {
        "count": len(props),
        "properties": [PropertyBrief.model_validate(p).model_dump(mode="json") for p in props],
    }


async def _get_property_details(args: PropertyIdArgs, ctx: ToolContext) -> Any:
    prop = await PropertyService(ctx.session).get(args.property_id)
    if prop.id not in ctx.property_ids:
        ctx.property_ids.append(prop.id)
    data = PropertyBrief.model_validate(prop).model_dump(mode="json")
    data.update(
        status=prop.status,
        address=prop.address,
        area_m2=str(prop.area_m2) if prop.area_m2 else None,
        floor=prop.floor,
        deposit=str(prop.deposit) if prop.deposit else None,
        utilities_included=prop.utilities_included,
        max_term_months=prop.max_term_months,
        description=prop.description,
        features=prop.features,
    )
    return data


async def _save_preferences(args: PropertySearchCriteria, ctx: ToolContext) -> Any:
    criteria = args.model_dump(mode="json", exclude_defaults=True, exclude={"limit", "exclude_ids"})
    lead = await LeadService(ctx.session).update_criteria(ctx.user, criteria)
    return {"saved": True, "preferences": lead.criteria}


async def _search_faq(args: FaqArgs, ctx: ToolContext) -> Any:
    entries = await FaqService(ctx.session).search(args.query, ctx.language)
    return {"results": [{"question": e.question, "answer": e.answer} for e in entries]}


async def _handoff(args: HandoffArgs, ctx: ToolContext) -> Any:
    lead = await LeadService(ctx.session).get_or_create(ctx.user)
    ticket = await TicketService(ctx.session).create(
        ctx.user,
        TicketCreate(
            category=args.category,
            priority=args.priority,
            summary=args.summary,
            context={
                "language": ctx.language,
                "criteria": lead.criteria,
                "property_ids": ctx.property_ids,
                "transcript": ctx.transcript[-10:],
            },
        ),
    )
    ctx.ticket_id = ticket.id
    return {"ticket_id": ticket.id, "status": "operator_notified"}


# ----------------------------------------------------------------- registry
Handler = Callable[[Any, ToolContext], Awaitable[Any]]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    args_model: type[BaseModel]
    handler: Handler

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name, description=self.description, parameters=inline_schema(self.args_model)
        )


def inline_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Pydantic JSON schema with `$defs` inlined — some LLM providers reject `$ref`."""
    schema = model.model_json_schema()
    defs = schema.pop("$defs", {})

    def resolve(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                return resolve(defs[node["$ref"].split("/")[-1]])
            return {k: resolve(v) for k, v in node.items() if k != "title"}
        if isinstance(node, list):
            return [resolve(v) for v in node]
        return node

    return resolve(schema)


class ToolRegistry:
    def __init__(self, tools: list[Tool]) -> None:
        self._tools = {t.name: t for t in tools}

    @property
    def definitions(self) -> list[ToolDefinition]:
        return [t.definition for t in self._tools.values()]

    async def execute(self, call: ToolCall, ctx: ToolContext) -> str:
        tool = self._tools.get(call.function.name)
        if tool is None:
            return json.dumps({"error": f"unknown tool {call.function.name}"})
        try:
            args = tool.args_model.model_validate_json(call.function.arguments or "{}")
        except PydanticValidationError as exc:
            return json.dumps(
                {"error": "invalid arguments", "details": exc.errors(include_url=False)}, default=str
            )

        log.info("ai.tool_call", tool=tool.name, args=args.model_dump(mode="json"))
        try:
            # savepoint: a failing tool must not poison the outer transaction
            async with ctx.session.begin_nested():
                result = await tool.handler(args, ctx)
        except DomikError as exc:
            return json.dumps({"error": exc.__class__.__name__, "message": str(exc)})
        except Exception:
            log.exception("ai.tool_failed", tool=tool.name)
            return json.dumps({"error": "internal_error"})
        return json.dumps(result, ensure_ascii=False, default=str)


def default_registry() -> ToolRegistry:
    return ToolRegistry(
        [
            Tool(
                "search_properties",
                "Search available rental properties by the client's criteria. "
                "Returns up to `limit` options sorted by price.",
                PropertySearchCriteria,
                _search_properties,
            ),
            Tool(
                "get_property_details",
                "Get full details of one property (description, deposit, address, conditions).",
                PropertyIdArgs,
                _get_property_details,
            ),
            Tool(
                "save_client_preferences",
                "Persist the client's stated search preferences to the CRM. Call whenever they change.",
                PropertySearchCriteria,
                _save_preferences,
            ),
            Tool(
                "search_faq",
                "Search the agency knowledge base for answers to typical questions.",
                FaqArgs,
                _search_faq,
            ),
            Tool(
                "handoff_to_operator",
                "Escalate the conversation to a human operator and create a support ticket.",
                HandoffArgs,
                _handoff,
            ),
        ]
    )
