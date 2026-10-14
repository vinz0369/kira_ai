from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlparse

import grpc
from google.protobuf.json_format import MessageToDict
from googleapiclient.discovery import build  # type: ignore[import-untyped]
from googleapiclient.errors import HttpError  # type: ignore[import-untyped]

from app.integrations.youtube.proto import stream_list_pb2, stream_list_pb2_grpc


@dataclass(frozen=True)
class YouTubeBatch:
    items: list[dict[str, Any]]
    next_page_token: str | None
    polling_interval_ms: int = 5000
    offline_at: str | None = None
    transport: str = "streamList"


@dataclass(frozen=True)
class ActiveBroadcast:
    id: str
    title: str
    live_chat_id: str
    actual_start_time: str | None
    life_cycle_status: str


class YouTubeProviderError(RuntimeError):
    def __init__(self, code: str, *, retryable: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


class StreamUnavailableError(YouTubeProviderError):
    def __init__(self, code: str = "stream_unavailable") -> None:
        super().__init__(code, retryable=False)


VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


def parse_video_id(value: str) -> str:
    """Accept a YouTube video ID or a known watch/live/share URL, never a fetch URL."""
    value = value.strip()
    if VIDEO_ID_RE.fullmatch(value):
        return value
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
        raise YouTubeProviderError("invalid_youtube_video")
    host = (parsed.hostname or "").lower()
    parts = [part for part in parsed.path.split("/") if part]
    video_id = ""
    if host in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
        if parsed.path == "/watch":
            video_id = (parse_qs(parsed.query).get("v") or [""])[0]
        elif len(parts) == 2 and parts[0] == "live":
            video_id = parts[1]
    elif host == "youtu.be" and len(parts) == 1:
        video_id = parts[0]
    elif host == "studio.youtube.com" and len(parts) >= 2 and parts[0] == "video":
        video_id = parts[1]
    if not VIDEO_ID_RE.fullmatch(video_id):
        raise YouTubeProviderError("invalid_youtube_video")
    return video_id


def build_youtube(credentials: Any) -> Any:
    return build(
        "youtube",
        "v3",
        credentials=credentials,
        cache_discovery=False,
        static_discovery=True,
    )


async def channel_identity(youtube: Any) -> tuple[str | None, str | None]:
    response = await asyncio.to_thread(
        youtube.channels().list(part="id,snippet", mine=True).execute
    )
    items = response.get("items", [])
    if not items:
        return None, None
    first = items[0]
    return str(first.get("id") or "") or None, str(
        first.get("snippet", {}).get("title") or ""
    ) or None


async def list_active_broadcasts(youtube: Any) -> list[ActiveBroadcast]:
    try:
        response = await asyncio.to_thread(
            youtube.liveBroadcasts()
            .list(
                part="id,snippet,status",
                broadcastStatus="active",
                broadcastType="all",
                maxResults=50,
            )
            .execute
        )
    except HttpError as exc:
        raise classify_http_error(exc) from exc
    result: list[ActiveBroadcast] = []
    for item in response.get("items", []):
        snippet = item.get("snippet", {})
        live_chat_id = str(snippet.get("liveChatId") or "")
        broadcast_id = str(item.get("id") or "")
        if not broadcast_id or not live_chat_id:
            continue
        result.append(
            ActiveBroadcast(
                id=broadcast_id,
                title=str(snippet.get("title") or "Untitled live"),
                live_chat_id=live_chat_id,
                actual_start_time=snippet.get("actualStartTime"),
                life_cycle_status=str(
                    item.get("status", {}).get("lifeCycleStatus") or "live"
                ),
            )
        )
    return result


async def resolve_active_broadcast(
    youtube: Any, broadcast_id: str
) -> ActiveBroadcast:
    broadcasts = await list_active_broadcasts(youtube)
    for broadcast in broadcasts:
        if broadcast.id == broadcast_id:
            return broadcast
    raise YouTubeProviderError("broadcast_not_active")


async def resolve_live_video(
    youtube: Any, value: str, expected_channel_id: str | None
) -> ActiveBroadcast:
    """Resolve an operator-supplied video against the connected channel and live chat."""
    video_id = parse_video_id(value)
    if not expected_channel_id:
        raise YouTubeProviderError("channel_identity_missing")
    try:
        response = await asyncio.to_thread(
            youtube.videos()
            .list(part="id,snippet,liveStreamingDetails", id=video_id)
            .execute
        )
    except HttpError as exc:
        raise classify_http_error(exc) from exc
    items = response.get("items", [])
    if not items:
        raise YouTubeProviderError("broadcast_not_found")
    item = items[0]
    snippet = item.get("snippet", {})
    if snippet.get("channelId") != expected_channel_id:
        raise YouTubeProviderError("broadcast_channel_mismatch")
    details = item.get("liveStreamingDetails", {})
    live_chat_id = str(details.get("activeLiveChatId") or "")
    if snippet.get("liveBroadcastContent") != "live":
        raise YouTubeProviderError("broadcast_not_active")
    if not live_chat_id:
        raise YouTubeProviderError("chat_unavailable")
    return ActiveBroadcast(
        id=video_id,
        title=str(snippet.get("title") or "YouTube Live"),
        live_chat_id=live_chat_id,
        actual_start_time=details.get("actualStartTime"),
        life_cycle_status="live",
    )


def classify_http_error(exc: HttpError) -> YouTubeProviderError:
    status = getattr(exc.resp, "status", None)
    reason = "youtube_api_error"
    try:
        body = json.loads(exc.content.decode())
        errors = body.get("error", {}).get("errors", [])
        if errors:
            reason = str(errors[0].get("reason") or reason)
    except (AttributeError, UnicodeDecodeError, json.JSONDecodeError):
        pass
    aliases = {
        "accessNotConfigured": "youtube_api_disabled",
        "quotaExceeded": "quota_exceeded",
        "dailyLimitExceeded": "quota_exceeded",
        "userRateLimitExceeded": "quota_exceeded",
        "rateLimitExceeded": "rate_limited",
        "liveChatDisabled": "chat_disabled",
        "liveChatEnded": "broadcast_ended",
        "liveChatNotFound": "chat_not_found",
        "insufficientPermissions": "insufficient_scope",
        "insufficientLivePermissions": "insufficient_scope",
        "authError": "auth_expired",
    }
    code = aliases.get(reason, reason)
    retryable = status is not None and int(status) >= 500
    return YouTubeProviderError(code, retryable=retryable)


def classify_grpc_error(exc: grpc.RpcError) -> YouTubeProviderError:
    code_method = getattr(exc, "code", None)
    status = code_method() if callable(code_method) else grpc.StatusCode.UNKNOWN
    if status == grpc.StatusCode.UNIMPLEMENTED:
        return StreamUnavailableError("stream_unimplemented")
    if status == grpc.StatusCode.RESOURCE_EXHAUSTED:
        return YouTubeProviderError("quota_or_rate_limited")
    if status == grpc.StatusCode.PERMISSION_DENIED:
        return YouTubeProviderError("insufficient_scope")
    if status == grpc.StatusCode.NOT_FOUND:
        return YouTubeProviderError("chat_not_found")
    if status == grpc.StatusCode.FAILED_PRECONDITION:
        return YouTubeProviderError("chat_disabled_or_ended")
    return YouTubeProviderError(
        "stream_connection_failed",
        retryable=status
        in {
            grpc.StatusCode.UNAVAILABLE,
            grpc.StatusCode.INTERNAL,
            grpc.StatusCode.DEADLINE_EXCEEDED,
        },
    )


class OfficialYouTubeProvider:
    def __init__(self, youtube: Any, access_token: str) -> None:
        self.youtube = youtube
        self.access_token = access_token

    async def stream_batches(
        self, live_chat_id: str, page_token: str | None
    ) -> AsyncIterator[YouTubeBatch]:
        credentials = grpc.ssl_channel_credentials()
        try:
            async with grpc.aio.secure_channel(
                "dns:///youtube.googleapis.com:443", credentials
            ) as channel:
                stub = stream_list_pb2_grpc.V3DataLiveChatMessageServiceStub(  # type: ignore[no-untyped-call]
                    channel
                )
                request_type = vars(stream_list_pb2)[
                    "LiveChatMessageListRequest"
                ]
                request = request_type(
                    live_chat_id=live_chat_id,
                    page_token=page_token or "",
                    part=["id", "snippet", "authorDetails"],
                )
                metadata = (("authorization", f"Bearer {self.access_token}"),)
                responses = stub.StreamList(request, metadata=metadata)
                async for response in responses:
                    payload = MessageToDict(response)
                    yield YouTubeBatch(
                        items=list(payload.get("items", [])),
                        next_page_token=payload.get("nextPageToken"),
                        offline_at=payload.get("offlineAt"),
                    )
        except grpc.RpcError as exc:
            raise classify_grpc_error(exc) from exc

    async def poll_batch(
        self, live_chat_id: str, page_token: str | None
    ) -> YouTubeBatch:
        try:
            kwargs: dict[str, Any] = {
                "liveChatId": live_chat_id,
                "part": "id,snippet,authorDetails",
                "maxResults": 2000,
                "hl": "vi",
            }
            if page_token:
                kwargs["pageToken"] = page_token
            response = await asyncio.to_thread(
                self.youtube.liveChatMessages().list(**kwargs).execute
            )
        except HttpError as exc:
            raise classify_http_error(exc) from exc
        return YouTubeBatch(
            items=list(response.get("items", [])),
            next_page_token=response.get("nextPageToken"),
            polling_interval_ms=max(
                1000, int(response.get("pollingIntervalMillis", 5000))
            ),
            offline_at=response.get("offlineAt"),
            transport="list",
        )
