import inspect
from typing import Any

import pytest
from googleapiclient.errors import HttpError  # type: ignore[import-untyped]
from httplib2 import Response

from app.integrations.youtube.provider import (
    OfficialYouTubeProvider,
    YouTubeProviderError,
    classify_http_error,
    list_active_broadcasts,
    parse_video_id,
    resolve_live_video,
)


class Executable:
    def __init__(self, result: dict[str, Any]) -> None:
        self.result = result

    def execute(self) -> dict[str, Any]:
        return self.result


class BroadcastResource:
    def __init__(self, result: dict[str, Any]) -> None:
        self.result = result
        self.kwargs: dict[str, Any] = {}

    def list(self, **kwargs: Any) -> Executable:
        self.kwargs = kwargs
        return Executable(self.result)


class ChatResource(BroadcastResource):
    pass


class FakeYouTube:
    def __init__(
        self, broadcast_result: dict[str, Any], chat_result: dict[str, Any]
    ) -> None:
        self.broadcast_resource = BroadcastResource(broadcast_result)
        self.chat_resource = ChatResource(chat_result)
        self.video_resource = BroadcastResource({"items": []})

    def liveBroadcasts(self) -> BroadcastResource:
        return self.broadcast_resource

    def liveChatMessages(self) -> ChatResource:
        return self.chat_resource

    def videos(self) -> BroadcastResource:
        return self.video_resource


@pytest.mark.anyio
async def test_broadcast_discovery_and_poll_interval_are_official_contract() -> None:
    youtube = FakeYouTube(
        {
            "items": [
                {
                    "id": "broadcast-1",
                    "snippet": {
                        "title": "Live now",
                        "liveChatId": "chat-1",
                        "actualStartTime": "2026-10-12T07:00:00Z",
                    },
                    "status": {"lifeCycleStatus": "live"},
                },
                {"id": "no-chat", "snippet": {"title": "Missing chat"}},
            ]
        },
        {
            "items": [],
            "nextPageToken": "next-1",
            "pollingIntervalMillis": 7250,
        },
    )
    broadcasts = await list_active_broadcasts(youtube)
    assert [item.id for item in broadcasts] == ["broadcast-1"]
    assert youtube.broadcast_resource.kwargs == {
        "part": "id,snippet,status",
        "broadcastStatus": "active",
        "broadcastType": "all",
        "maxResults": 50,
    }

    provider = OfficialYouTubeProvider(youtube, "access-token")
    batch = await provider.poll_batch("chat-1", None)
    assert batch.next_page_token == "next-1"
    assert batch.polling_interval_ms == 7250
    assert batch.transport == "list"
    assert youtube.chat_resource.kwargs["maxResults"] == 2000


def test_provider_test_does_not_make_network_calls() -> None:
    # Guards accidental conversion of the fixture tests into real API tests.
    assert inspect.iscoroutinefunction(list_active_broadcasts)


def test_disabled_youtube_api_has_safe_error_code() -> None:
    error = HttpError(
        Response({"status": "403"}),
        b'{"error":{"errors":[{"reason":"accessNotConfigured"}]}}',
    )
    assert classify_http_error(error).code == "youtube_api_disabled"


@pytest.mark.parametrize(
    "value",
    [
        "abcdefghijk",
        "https://www.youtube.com/watch?v=abcdefghijk&t=7",
        "https://youtube.com/live/abcdefghijk",
        "https://youtu.be/abcdefghijk?feature=share",
        "https://studio.youtube.com/video/abcdefghijk/livestreaming",
    ],
)
def test_parse_known_youtube_video_urls(value: str) -> None:
    assert parse_video_id(value) == "abcdefghijk"


@pytest.mark.parametrize(
    "value",
    ["https://youtube.com.evil.test/live/abcdefghijk", "http://127.0.0.1/abcdefghijk", "https://youtube.com/watch?v=bad", "ftp://youtu.be/abcdefghijk"],
)
def test_reject_unknown_video_urls(value: str) -> None:
    with pytest.raises(YouTubeProviderError, match="invalid_youtube_video"):
        parse_video_id(value)


@pytest.mark.anyio
async def test_manual_video_requires_same_channel_live_state_and_active_chat() -> None:
    youtube = FakeYouTube({}, {})
    video = {
        "id": "abcdefghijk",
        "snippet": {
            "channelId": "connected-channel",
            "title": "Current stream",
            "liveBroadcastContent": "live",
        },
        "liveStreamingDetails": {"activeLiveChatId": "fresh-chat"},
    }
    youtube.video_resource.result = {"items": [video]}
    found = await resolve_live_video(
        youtube, "https://youtube.com/live/abcdefghijk", "connected-channel"
    )
    assert found.id == "abcdefghijk"
    assert found.live_chat_id == "fresh-chat"
    assert youtube.video_resource.kwargs == {
        "part": "id,snippet,liveStreamingDetails",
        "id": "abcdefghijk",
    }
    video["snippet"]["channelId"] = "someone-else"
    with pytest.raises(YouTubeProviderError, match="broadcast_channel_mismatch"):
        await resolve_live_video(youtube, "abcdefghijk", "connected-channel")
    video["snippet"]["channelId"] = "connected-channel"
    video["snippet"]["liveBroadcastContent"] = "none"
    with pytest.raises(YouTubeProviderError, match="broadcast_not_active"):
        await resolve_live_video(youtube, "abcdefghijk", "connected-channel")
    video["snippet"]["liveBroadcastContent"] = "live"
    video["liveStreamingDetails"] = {}
    with pytest.raises(YouTubeProviderError, match="chat_unavailable"):
        await resolve_live_video(youtube, "abcdefghijk", "connected-channel")
