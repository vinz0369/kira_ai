import uuid
from datetime import UTC, datetime

from pydantic import EmailStr
from sqlalchemy import BigInteger, Text, UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

from app.live.avatar_assets import DEFAULT_AVATAR_ASSET_ID


def get_datetime_utc() -> datetime:
    return datetime.now(UTC)


# Shared properties
class UserBase(SQLModel):
    email: EmailStr = Field(unique=True, index=True, max_length=255)
    is_active: bool = True
    is_superuser: bool = False
    full_name: str | None = Field(default=None, max_length=255)


# Properties to receive via API on creation
class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=128)


class UserRegister(SQLModel):
    email: EmailStr = Field(max_length=255)
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)


# Properties to receive via API on update, all are optional
class UserUpdate(SQLModel):
    email: EmailStr | None = Field(default=None, max_length=255)
    is_active: bool | None = None
    is_superuser: bool | None = None
    full_name: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, min_length=8, max_length=128)


class UserUpdateMe(SQLModel):
    full_name: str | None = Field(default=None, max_length=255)
    email: EmailStr | None = Field(default=None, max_length=255)


class UpdatePassword(SQLModel):
    current_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


# Database model, database table inferred from class name
class User(UserBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    hashed_password: str
    created_at: datetime | None = Field(default_factory=get_datetime_utc)
    items: list[Item] = Relationship(back_populates="owner", cascade_delete=True)
    characters: list[Character] = Relationship(
        back_populates="owner", cascade_delete=True
    )
    live_sessions: list[LiveSession] = Relationship(
        back_populates="owner", cascade_delete=True
    )
    oauth_connections: list[OAuthConnection] = Relationship(
        back_populates="owner", cascade_delete=True
    )


# Properties to return via API, id is always required
class UserPublic(UserBase):
    id: uuid.UUID
    created_at: datetime | None = None


class UsersPublic(SQLModel):
    data: list[UserPublic]
    count: int


# Shared properties
class ItemBase(SQLModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=255)


# Properties to receive on item creation
class ItemCreate(ItemBase):
    pass


# Properties to receive on item update
class ItemUpdate(SQLModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=255)


# Database model, database table inferred from class name
class Item(ItemBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    created_at: datetime | None = Field(default_factory=get_datetime_utc)
    owner_id: uuid.UUID = Field(
        foreign_key="user.id", nullable=False, ondelete="CASCADE"
    )
    owner: User | None = Relationship(back_populates="items")


class CharacterBase(SQLModel):
    name: str = Field(min_length=1, max_length=80)
    template_id: str = Field(default="balanced-friend", max_length=50)
    persona_description: str = Field(default="Bạn thân tinh nghịch", max_length=1200)
    address_streamer_as: str = Field(default="bạn", max_length=40)
    viewer_style: str = Field(default="thân thiện", max_length=120)
    humor_level: str = Field(default="balanced", max_length=20)
    proactivity: str = Field(default="balanced", max_length=20)
    llm_provider: str = Field(default="fake", max_length=30)
    llm_model: str = Field(default="mock-template", max_length=120)
    voice_provider: str = Field(default="fake", max_length=30)
    voice_id: str = Field(default="mock-sine", max_length=80)
    avatar_asset_id: str | None = Field(default=DEFAULT_AVATAR_ASSET_ID, max_length=255)
    avatar_camera_framing: str = Field(default="chest-up", max_length=20)
    avatar_camera_zoom: float = Field(default=1.0, ge=0.7, le=1.5)
    memory_opt_in: bool = False


class Character(CharacterBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    owner_id: uuid.UUID = Field(
        foreign_key="user.id", nullable=False, ondelete="CASCADE", index=True
    )
    created_at: datetime = Field(default_factory=get_datetime_utc)
    updated_at: datetime = Field(default_factory=get_datetime_utc)
    owner: User | None = Relationship(back_populates="characters")
    live_sessions: list[LiveSession] = Relationship(back_populates="character")


class LiveSession(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    owner_id: uuid.UUID = Field(
        foreign_key="user.id", nullable=False, ondelete="CASCADE", index=True
    )
    character_id: uuid.UUID = Field(
        foreign_key="character.id", nullable=False, ondelete="CASCADE", index=True
    )
    mode: str = Field(default="mock", max_length=20)
    voice_mode: str = Field(default="mock", max_length=20)
    status: str = Field(default="draft", max_length=20, index=True)
    ai_muted: bool = True
    mic_connected: bool = False
    session_epoch: int = 0
    overlay_key_hash: str | None = Field(default=None, max_length=64)
    youtube_broadcast_id: str | None = Field(default=None, max_length=255, index=True)
    youtube_live_chat_id: str | None = Field(default=None, max_length=255)
    youtube_next_page_token: str | None = Field(default=None, sa_type=Text)
    youtube_ingest_status: str = Field(default="disabled", max_length=30)
    youtube_last_error: str | None = Field(default=None, max_length=80)
    youtube_connected_at: datetime | None = None
    created_at: datetime = Field(default_factory=get_datetime_utc)
    started_at: datetime | None = None
    stopped_at: datetime | None = None
    updated_at: datetime = Field(default_factory=get_datetime_utc)
    owner: User | None = Relationship(back_populates="live_sessions")
    character: Character | None = Relationship(back_populates="live_sessions")
    paid_events: list[PaidEvent] = Relationship(
        back_populates="live_session", cascade_delete=True
    )


class PaidEvent(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint(
            "live_session_id", "provider_event_id", name="uq_paid_event_provider"
        ),
    )
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    live_session_id: uuid.UUID = Field(
        foreign_key="livesession.id", nullable=False, ondelete="CASCADE", index=True
    )
    provider_event_id: str = Field(max_length=255, index=True)
    event_type: str = Field(max_length=40)
    author_display_name: str = Field(default="Người xem", max_length=255)
    amount_micros: int = Field(default=0, ge=0, sa_type=BigInteger)
    currency: str = Field(default="VND", min_length=3, max_length=3)
    ack_status: str = Field(default="pending", max_length=20)
    created_at: datetime = Field(default_factory=get_datetime_utc)
    live_session: LiveSession | None = Relationship(back_populates="paid_events")


class OAuthConnection(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint("owner_id", "provider", name="uq_oauth_owner_provider"),
    )
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    owner_id: uuid.UUID = Field(
        foreign_key="user.id", nullable=False, ondelete="CASCADE", index=True
    )
    provider: str = Field(default="google_youtube", max_length=40)
    encrypted_access_token: str = Field(sa_type=Text)
    encrypted_refresh_token: str | None = Field(default=None, sa_type=Text)
    expires_at: datetime | None = None
    granted_scopes: str = Field(default="", max_length=1024)
    provider_channel_id: str | None = Field(default=None, max_length=255)
    provider_channel_name: str | None = Field(default=None, max_length=255)
    status: str = Field(default="connected", max_length=30)
    last_error_code: str | None = Field(default=None, max_length=80)
    created_at: datetime = Field(default_factory=get_datetime_utc)
    updated_at: datetime = Field(default_factory=get_datetime_utc)
    owner: User | None = Relationship(back_populates="oauth_connections")


class OAuthAttempt(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    owner_id: uuid.UUID = Field(
        foreign_key="user.id", nullable=False, ondelete="CASCADE", index=True
    )
    state_hash: str = Field(unique=True, index=True, max_length=64)
    encrypted_code_verifier: str = Field(sa_type=Text)
    expires_at: datetime
    consumed_at: datetime | None = None
    created_at: datetime = Field(default_factory=get_datetime_utc)


class YouTubeEventReceipt(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint(
            "live_session_id",
            "provider_message_id",
            name="uq_youtube_receipt_provider",
        ),
    )
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    live_session_id: uuid.UUID = Field(
        foreign_key="livesession.id", nullable=False, ondelete="CASCADE", index=True
    )
    provider_message_id: str = Field(max_length=255, index=True)
    event_type: str = Field(max_length=40)
    published_at: datetime | None = None
    is_historical: bool = False
    created_at: datetime = Field(default_factory=get_datetime_utc)


# Properties to return via API, id is always required
class ItemPublic(ItemBase):
    id: uuid.UUID
    owner_id: uuid.UUID
    created_at: datetime | None = None


class ItemsPublic(SQLModel):
    data: list[ItemPublic]
    count: int


# Generic message
class Message(SQLModel):
    message: str


# JSON payload containing access token
class Token(SQLModel):
    access_token: str
    token_type: str = "bearer"


# Contents of JWT token
class TokenPayload(SQLModel):
    sub: str | None = None


class NewPassword(SQLModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)
