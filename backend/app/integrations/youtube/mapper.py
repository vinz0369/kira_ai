from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.live.contracts import EventEnvelope


@dataclass(frozen=True)
class MappedYouTubeEvent:
    envelope: EventEnvelope
    provider_message_id: str
    published_at: datetime | None
    is_paid: bool


def _clean_text(value: Any, limit: int = 500) -> str:
    if not isinstance(value, str):
        return ""
    return value.replace("\x00", "").strip()[:limit]


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC)


def map_live_chat_item(
    item: dict[str, Any], session_id: Any
) -> MappedYouTubeEvent | None:
    provider_id = _clean_text(item.get("id"), 255)
    snippet = item.get("snippet")
    author = item.get("authorDetails") or item.get("author_details") or {}
    if not provider_id or not isinstance(snippet, dict) or not isinstance(author, dict):
        return None

    raw_type = snippet.get("type")
    type_aliases = {
        "TEXT_MESSAGE_EVENT": "textMessageEvent",
        "SUPER_CHAT_EVENT": "superChatEvent",
        "SUPER_STICKER_EVENT": "superStickerEvent",
        "CHAT_ENDED_EVENT": "chatEndedEvent",
    }
    message_type = type_aliases.get(str(raw_type), str(raw_type))
    author_name = _clean_text(
        author.get("displayName") or author.get("display_name"), 255
    ) or "Người xem"
    author_channel_id = _clean_text(
        author.get("channelId")
        or author.get("channel_id")
        or snippet.get("authorChannelId")
        or snippet.get("author_channel_id"),
        255,
    )
    published_at = _parse_timestamp(
        snippet.get("publishedAt") or snippet.get("published_at")
    )
    event_ts = published_at or datetime.now(UTC)

    if message_type == "textMessageEvent":
        details = snippet.get("textMessageDetails") or snippet.get(
            "text_message_details"
        )
        if not isinstance(details, dict):
            details = {}
        text = _clean_text(
            details.get("messageText")
            or details.get("message_text")
            or snippet.get("displayMessage")
            or snippet.get("display_message")
        )
        if not text:
            return None
        payload: dict[str, Any] = {
            "provider_message_id": provider_id,
            "author_channel_id": author_channel_id,
            "author_name": author_name,
            "text": text,
        }
        event_type = "youtube.chat.message"
        is_paid = False
    elif message_type in {"superChatEvent", "superStickerEvent"}:
        details_key = (
            ("superChatDetails", "super_chat_details")
            if message_type == "superChatEvent"
            else ("superStickerDetails", "super_sticker_details")
        )
        details = snippet.get(details_key[0]) or snippet.get(details_key[1])
        if not isinstance(details, dict):
            return None
        raw_amount = details.get("amountMicros", details.get("amount_micros", 0))
        try:
            amount_micros = int(raw_amount or 0)
        except (TypeError, ValueError):
            return None
        currency = _clean_text(details.get("currency"), 3).upper()
        if amount_micros < 0 or len(currency) != 3 or not currency.isalpha():
            return None
        display_string = _clean_text(
            details.get("amountDisplayString")
            or details.get("amount_display_string"),
            80,
        )
        payload = {
            "provider_message_id": provider_id,
            "author_channel_id": author_channel_id,
            "author_name": author_name,
            "amount_micros": amount_micros,
            "currency": currency,
            "amount_display_string": display_string,
        }
        if message_type == "superChatEvent":
            payload["text"] = _clean_text(
                details.get("userComment") or details.get("user_comment")
            )
            event_type = "youtube.superchat"
        else:
            metadata = details.get("superStickerMetadata") or details.get(
                "super_sticker_metadata"
            )
            if not isinstance(metadata, dict):
                metadata = {}
            payload["alt_text"] = _clean_text(
                metadata.get("altText") or metadata.get("alt_text")
            )
            event_type = "youtube.supersticker"
        is_paid = True
    else:
        return None

    return MappedYouTubeEvent(
        envelope=EventEnvelope(
            session_id=session_id,
            type=event_type,
            ts=event_ts,
            source="youtube",
            payload=payload,
        ),
        provider_message_id=provider_id,
        published_at=published_at,
        is_paid=is_paid,
    )
