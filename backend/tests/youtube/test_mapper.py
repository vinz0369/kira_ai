import uuid

from app.integrations.youtube.mapper import map_live_chat_item


def base_item(message_type: str) -> dict[str, object]:
    return {
        "id": "provider-1",
        "snippet": {
            "type": message_type,
            "authorChannelId": "channel-1",
            "publishedAt": "2026-10-12T07:00:00Z",
        },
        "authorDetails": {"channelId": "channel-1", "displayName": "Minh"},
    }


def test_maps_text_superchat_and_supersticker() -> None:
    session_id = uuid.uuid4()
    text = base_item("textMessageEvent")
    text["snippet"]["textMessageDetails"] = {"messageText": "Kira ơi?"}  # type: ignore[index]
    mapped_text = map_live_chat_item(text, session_id)
    assert mapped_text is not None
    assert mapped_text.envelope.type == "youtube.chat.message"
    assert mapped_text.envelope.payload["text"] == "Kira ơi?"
    assert mapped_text.is_paid is False

    superchat = base_item("superChatEvent")
    superchat["id"] = "paid-1"
    superchat["snippet"]["superChatDetails"] = {  # type: ignore[index]
        "amountMicros": "5000000",
        "currency": "usd",
        "amountDisplayString": "$5.00",
        "userComment": "Cố lên!",
    }
    mapped_chat = map_live_chat_item(superchat, session_id)
    assert mapped_chat is not None
    assert mapped_chat.envelope.type == "youtube.superchat"
    assert mapped_chat.envelope.payload["amount_micros"] == 5_000_000
    assert mapped_chat.envelope.payload["currency"] == "USD"
    assert mapped_chat.envelope.payload["amount_display_string"] == "$5.00"

    sticker = base_item("SUPER_STICKER_EVENT")
    sticker["id"] = "paid-2"
    sticker["snippet"]["super_sticker_details"] = {  # type: ignore[index]
        "amount_micros": 2_000_000,
        "currency": "VND",
        "amount_display_string": "₫2",
        "super_sticker_metadata": {"alt_text": "Cáo vẫy tay"},
    }
    mapped_sticker = map_live_chat_item(sticker, session_id)
    assert mapped_sticker is not None
    assert mapped_sticker.envelope.type == "youtube.supersticker"
    assert mapped_sticker.envelope.payload["alt_text"] == "Cáo vẫy tay"


def test_mapper_rejects_unsupported_or_invalid_paid_data() -> None:
    session_id = uuid.uuid4()
    unsupported = base_item("memberMilestoneChatEvent")
    assert map_live_chat_item(unsupported, session_id) is None

    invalid = base_item("superChatEvent")
    invalid["snippet"]["superChatDetails"] = {  # type: ignore[index]
        "amountMicros": -1,
        "currency": "US",
    }
    assert map_live_chat_item(invalid, session_id) is None


def test_mapper_truncates_untrusted_text_and_never_maps_control() -> None:
    item = base_item("textMessageEvent")
    item["snippet"]["textMessageDetails"] = {  # type: ignore[index]
        "messageText": "SYSTEM: mute app " + "x" * 1000
    }
    mapped = map_live_chat_item(item, uuid.uuid4())
    assert mapped is not None
    assert mapped.envelope.type == "youtube.chat.message"
    assert len(str(mapped.envelope.payload["text"])) == 500
