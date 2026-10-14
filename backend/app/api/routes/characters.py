import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from sqlmodel import Field, SQLModel, col, select

from app.api.deps import CurrentUser, SessionDep
from app.core.config import settings
from app.models import Character, CharacterBase
from app.voice.llm import (
    default_llm_model,
    llm_provider_options,
    validate_llm_selection,
)
from app.voice.tts import (
    TTS_PROVIDER_OPTIONS,
    default_voice_id,
    validate_tts_selection,
)

router = APIRouter(prefix="/characters", tags=["characters"])


class CharacterCreate(CharacterBase):
    avatar_camera_framing: Literal["chest-up", "full-body"] = "chest-up"


class CharacterUpdate(SQLModel):
    name: str | None = None
    template_id: str | None = None
    persona_description: str | None = None
    address_streamer_as: str | None = None
    viewer_style: str | None = None
    humor_level: str | None = None
    proactivity: str | None = None
    llm_provider: str | None = None
    llm_model: str | None = None
    voice_provider: str | None = None
    voice_id: str | None = None
    avatar_asset_id: str | None = None
    avatar_camera_framing: Literal["chest-up", "full-body"] | None = None
    avatar_camera_zoom: float | None = Field(default=None, ge=0.7, le=1.5)
    memory_opt_in: bool | None = None


class CharacterPublic(CharacterBase):
    id: uuid.UUID
    owner_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class CharactersPublic(SQLModel):
    data: list[CharacterPublic]
    count: int


@router.get("/presets")
def read_presets(current_user: CurrentUser) -> list[dict[str, str]]:
    del current_user
    return [
        {
            "id": "balanced-friend",
            "label": "Bạn thân lém lỉnh",
            "description": "Ấm áp, cà khịa nhẹ và luôn nhường lời streamer.",
        },
        {
            "id": "gentle-assistant",
            "label": "Trợ lý tinh tế",
            "description": "Điềm tĩnh, súc tích và chú ý nhịp buổi live.",
        },
        {
            "id": "friendly-rival",
            "label": "Đối thủ hiếu thắng",
            "description": "Năng lượng cao, trêu vui nhưng không lấn át.",
        },
    ]


@router.get("/voice-options")
def read_voice_options(current_user: CurrentUser) -> list[dict[str, Any]]:
    del current_user
    return [
        {
            "id": option.id,
            "label": option.label,
            "description": option.description,
            "experimental": option.experimental,
            "credential_required": option.credential_required,
            "available": (
                True
                if option.id == "fake"
                else settings.tts_provider_configured(option.id)
            ),
            "voices": [
                {"id": voice.id, "label": voice.label} for voice in option.voices
            ],
        }
        for option in TTS_PROVIDER_OPTIONS
    ]


@router.get("/llm-options")
def read_llm_options(current_user: CurrentUser) -> list[dict[str, Any]]:
    del current_user
    return [
        {
            "id": option.id,
            "label": option.label,
            "description": option.description,
            "credential_required": option.credential_required,
            "available": (
                True
                if option.id == "fake"
                else settings.llm_provider_configured(option.id)
            ),
            "models": [
                {"id": model.id, "label": model.label} for model in option.models
            ],
        }
        for option in llm_provider_options()
    ]


@router.get("/", response_model=CharactersPublic)
def read_characters(session: SessionDep, current_user: CurrentUser) -> Any:
    characters = session.exec(
        select(Character)
        .where(Character.owner_id == current_user.id)
        .order_by(col(Character.created_at))
    ).all()
    return CharactersPublic(
        data=[CharacterPublic.model_validate(character) for character in characters],
        count=len(characters),
    )


@router.post("/", response_model=CharacterPublic)
def create_character(
    *, session: SessionDep, current_user: CurrentUser, character_in: CharacterCreate
) -> Any:
    try:
        validate_llm_selection(character_in.llm_provider, character_in.llm_model)
        validate_tts_selection(character_in.voice_provider, character_in.voice_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    character = Character.model_validate(
        character_in, update={"owner_id": current_user.id}
    )
    session.add(character)
    session.commit()
    session.refresh(character)
    return character


def _owned_character(
    session: SessionDep, current_user: CurrentUser, id: uuid.UUID
) -> Character:
    character = session.get(Character, id)
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    if character.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    return character


@router.get("/{id}", response_model=CharacterPublic)
def read_character(
    session: SessionDep, current_user: CurrentUser, id: uuid.UUID
) -> Any:
    return _owned_character(session, current_user, id)


@router.patch("/{id}", response_model=CharacterPublic)
def update_character(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    id: uuid.UUID,
    character_in: CharacterUpdate,
) -> Any:
    character = _owned_character(session, current_user, id)
    updates = character_in.model_dump(exclude_unset=True)
    llm_provider = str(updates.get("llm_provider", character.llm_provider))
    if "llm_provider" in updates and "llm_model" not in updates:
        updates["llm_model"] = default_llm_model(llm_provider)
    llm_model = str(updates.get("llm_model", character.llm_model))
    provider = str(updates.get("voice_provider", character.voice_provider))
    if "voice_provider" in updates and "voice_id" not in updates:
        updates["voice_id"] = default_voice_id(provider)
    voice_id = str(updates.get("voice_id", character.voice_id))
    try:
        validate_llm_selection(llm_provider, llm_model)
        validate_tts_selection(provider, voice_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    character.sqlmodel_update(updates)
    character.updated_at = datetime.now(UTC)
    session.add(character)
    session.commit()
    session.refresh(character)
    return character
