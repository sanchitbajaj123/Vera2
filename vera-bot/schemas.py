from typing import Any, Optional
from pydantic import BaseModel


class ContextBody(BaseModel):
    scope: str
    context_id: str
    version: int = 1
    payload: dict[str, Any] = {}
    delivered_at: Optional[str] = None


class TickBody(BaseModel):
    now: Optional[str] = None
    available_triggers: list[str] = []


class ReplyBody(BaseModel):
    conversation_id: str
    merchant_id: Optional[str] = None
    customer_id: Optional[str] = None
    from_role: str = "merchant"
    message: str = ""
    received_at: Optional[str] = None
    turn_number: int = 1
