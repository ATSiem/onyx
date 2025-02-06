from typing import Any
from typing import List
from typing import Optional

from pydantic import BaseModel
from pydantic import Field


class Message(BaseModel):
    id: int
    sender_id: int
    content: str
    subject: str
    stream_id: int
    sender_full_name: str
    display_recipient: str
    timestamp: int = 0
    last_edit_timestamp: Optional[int] = None
    recipient_id: Optional[int] = None
    client: Optional[str] = None
    is_me_message: Optional[bool] = None
    sender_email: Optional[str] = None
    sender_realm_str: Optional[str] = None
    topic_links: Optional[List[Any]] = None
    edit_history: Optional[Any] = None
    reactions: List[Any] = Field(default_factory=list)
    submessages: List[Any] = Field(default_factory=list)
    flags: List[str] = Field(default_factory=list)
    type: Optional[str] = None
    avatar_url: Optional[str] = None
    content_type: Optional[str] = None
    rendered_content: Optional[str] = None

    class Config:
        extra = "allow"


class GetMessagesResponse(BaseModel):
    result: str
    msg: str
    messages: List[Message]
    found_oldest: bool = False
    anchor: Any = None
    found_anchor: Optional[bool] = None
    found_newest: Optional[bool] = None
    history_limited: Optional[bool] = None

    class Config:
        extra = "allow"


class ZulipConfig(BaseModel):
    realm_name: str
    base_url: str
