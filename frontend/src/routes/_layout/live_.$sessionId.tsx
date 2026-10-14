import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { createFileRoute, Link } from "@tanstack/react-router"
import {
  Copy,
  ExternalLink,
  Mic,
  Pause,
  Play,
  RefreshCw,
  Square,
  Volume2,
  VolumeX,
} from "lucide-react"
import { useCallback, useEffect, useRef, useState } from "react"

import { MockBadge } from "@/components/Live/MockBadge"
import { useVoiceMic } from "@/components/Live/useVoiceMic"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  type LiveEvent,
  liveApi,
  websocketBase,
  type YouTubeBroadcast,
} from "@/lib/liveApi"
import {
  friendlyLiveError,
  sessionModeLabel,
  sessionStatusLabel,
  youtubeStatusLabel,
} from "@/lib/liveUi"

export const Route = createFileRoute("/_layout/live_/$sessionId")({
  component: LiveDashboard,
})

function useDashboardSocket(sessionId: string, enabled: boolean) {
  const [events, setEvents] = useState<LiveEvent[]>([])
  const [connected, setConnected] = useState(false)
  const socketRef = useRef<WebSocket | null>(null)
  useEffect(() => {
    if (!enabled) return
    let socket: WebSocket | null = null
    let stopped = false
    let retry: ReturnType<typeof setTimeout> | undefined
    let attempts = 0
    const connect = async () => {
      try {
        const { ticket } = await liveApi.ticket(sessionId)
        if (stopped) return
        socket = new WebSocket(
          `${websocketBase()}/ws/v1/dashboard/${sessionId}?ticket=${encodeURIComponent(ticket)}`,
        )
        socket.binaryType = "arraybuffer"
        socketRef.current = socket
        socket.onopen = () => {
          attempts = 0
          setConnected(true)
        }
        socket.onmessage = (message) => {
          const event = JSON.parse(message.data) as LiveEvent
          if (event.type !== "pong")
            setEvents((current) => [event, ...current].slice(0, 200))
        }
        socket.onclose = () => {
          setConnected(false)
          if (!stopped)
            retry = setTimeout(connect, Math.min(5000, 500 * 2 ** attempts++))
        }
      } catch {
        if (!stopped)
          retry = setTimeout(connect, Math.min(5000, 500 * 2 ** attempts++))
      }
    }
    void connect()
    return () => {
      stopped = true
      if (retry) clearTimeout(retry)
      socket?.close()
      socketRef.current = null
    }
  }, [enabled, sessionId])
  const send = useCallback((data: string | ArrayBuffer) => {
    const socket = socketRef.current
    if (!socket || socket.readyState !== WebSocket.OPEN) return false
    if (socket.bufferedAmount > 256_000) return false
    socket.send(data)
    return true
  }, [])
  return { events, connected, send }
}

function LiveDashboard() {
  const { sessionId } = Route.useParams()
  const queryClient = useQueryClient()
  const session = useQuery({
    queryKey: ["session", sessionId],
    queryFn: () => liveApi.getSession(sessionId),
    refetchInterval: 5000,
  })
  const character = useQuery({
    queryKey: ["character", session.data?.character_id],
    queryFn: () => liveApi.getCharacter(session.data!.character_id),
    enabled: Boolean(session.data?.character_id),
  })
  const usage = useQuery({
    queryKey: ["usage", sessionId],
    queryFn: () => liveApi.usage(sessionId),
    refetchInterval: 3000,
  })
  const activeBroadcasts = useQuery({
    queryKey: ["youtube-broadcasts"],
    queryFn: liveApi.youtubeBroadcasts,
    enabled:
      session.data?.mode === "youtube" && session.data.status !== "stopped",
    refetchInterval: 15_000,
  })
  const {
    events,
    connected,
    send: sendSocket,
  } = useDashboardSocket(sessionId, session.data?.status !== "stopped")
  const mic = useVoiceMic(
    sessionId,
    connected && session.data?.voice_mode === "real",
    sendSocket,
  )
  const [transcript, setTranscript] = useState(
    "Kira, mày nghĩ tao thắng trận này không?",
  )
  const [viewerText, setViewerText] = useState(
    "Kira, bạn cổ vũ streamer được không?",
  )
  const [donor, setDonor] = useState("Minh")
  const [error, setError] = useState("")
  const [confirmStop, setConfirmStop] = useState(false)
  const [activeMotion, setActiveMotion] = useState<
    "idle" | "greet" | "heart" | "dance"
  >("idle")
  const motionTimer = useRef<ReturnType<typeof setTimeout> | undefined>(
    undefined,
  )
  const avatarMotion = useMutation({
    mutationFn: (request: {
      motion: "idle" | "greet" | "heart" | "dance"
      durationSeconds: number
    }) =>
      liveApi.avatarMotion(sessionId, request.motion, request.durationSeconds),
    onSuccess: (result) => {
      if (motionTimer.current) clearTimeout(motionTimer.current)
      const motion = result.motion as typeof activeMotion
      setActiveMotion(motion)
      if (result.duration_seconds > 0)
        motionTimer.current = setTimeout(
          () => setActiveMotion("idle"),
          result.duration_seconds * 1000,
        )
    },
    onError: (cause: Error) => setError(friendlyLiveError(cause)),
  })
  useEffect(() => {
    const latest = events[0]
    if (
      latest?.type === "overlay.connected" ||
      latest?.type === "overlay.disconnected"
    ) {
      if (motionTimer.current) clearTimeout(motionTimer.current)
      setActiveMotion("idle")
    } else if (latest?.type === "avatar.motion") {
      if (motionTimer.current) clearTimeout(motionTimer.current)
      const next = latest.payload.motion
      const motion =
        next === "greet" || next === "heart" || next === "dance" ? next : "idle"
      setActiveMotion(motion)
      const duration = Number(latest.payload.duration_seconds ?? 0)
      if (duration > 0)
        motionTimer.current = setTimeout(
          () => setActiveMotion("idle"),
          duration * 1000,
        )
    } else if (
      latest?.type === "session.control" &&
      ["pause", "stop"].includes(String(latest.payload.command))
    ) {
      if (motionTimer.current) clearTimeout(motionTimer.current)
      setActiveMotion("idle")
    }
  }, [events])
  useEffect(
    () => () => {
      if (motionTimer.current) clearTimeout(motionTimer.current)
    },
    [],
  )
  const [videoUrl, setVideoUrl] = useState("")
  const [resolvedBroadcast, setResolvedBroadcast] =
    useState<YouTubeBroadcast | null>(null)
  const [lastDecision, setLastDecision] = useState("")
  const overlayUrl =
    session.data?.status === "stopped"
      ? null
      : sessionStorage.getItem(`overlay:${sessionId}`)
  const latestState = events.find((event) => event.type === "session.state")
  const overlayConnected = Boolean(latestState?.payload.overlay_connected)
  const sttConnected = Boolean(latestState?.payload.mic_connected)
  const control = useMutation({
    mutationFn: (command: string) => liveApi.control(sessionId, command),
    onSuccess: (data, command) => {
      queryClient.setQueryData(["session", sessionId], data)
      void queryClient.invalidateQueries({ queryKey: ["current-live-session"] })
      void queryClient.invalidateQueries({ queryKey: ["live-sessions"] })
      setConfirmStop(false)
      setError("")
      if (command === "stop") sessionStorage.removeItem(`overlay:${sessionId}`)
    },
    onError: (cause: Error) => setError(friendlyLiveError(cause)),
  })
  const simulate = useMutation({
    mutationFn: ({
      type,
      payload,
    }: {
      type: string
      payload: Record<string, unknown>
    }) => liveApi.simulate(sessionId, type, payload),
    onSuccess: (result) => {
      const decision = result.events.find(
        (event) => event.type === "director.decision",
      )
      setLastDecision(
        decision
          ? `${decision.payload.decision}: ${decision.payload.reason_code}`
          : "accepted",
      )
    },
    onError: (cause: Error) => setError(friendlyLiveError(cause)),
  })
  const rotate = useMutation({
    mutationFn: () => liveApi.rotateOverlayKey(sessionId),
    onSuccess: (data) => {
      if (data.overlay_url)
        sessionStorage.setItem(`overlay:${sessionId}`, data.overlay_url)
      window.location.reload()
    },
    onError: (cause: Error) => setError(friendlyLiveError(cause)),
  })
  const reconnect = useMutation({
    mutationFn: () => liveApi.reconnectYoutube(sessionId),
    onSuccess: (data) => {
      queryClient.setQueryData(["session", sessionId], data)
      setError("")
    },
    onError: (cause: Error) => setError(friendlyLiveError(cause)),
  })
  const resolveBroadcast = useMutation({
    mutationFn: () => liveApi.resolveYoutubeBroadcast(videoUrl),
    onSuccess: setResolvedBroadcast,
  })
  const bindBroadcast = useMutation({
    mutationFn: () => liveApi.bindYoutubeBroadcast(sessionId, videoUrl),
    onSuccess: (data) => {
      queryClient.setQueryData(["session", sessionId], data)
      setResolvedBroadcast(null)
      setVideoUrl("")
      setError("")
    },
    onError: (cause: Error) => setError(friendlyLiveError(cause)),
  })
  const send = useCallback(
    (type: string, payload: Record<string, unknown>) => {
      setError("")
      simulate.mutate({ type, payload })
    },
    [simulate],
  )
  if (session.isPending) return <p>Đang tải phiên live…</p>
  if (session.error || !session.data) {
    return (
      <Alert variant="destructive">
        <AlertTitle>Không mở được phiên live</AlertTitle>
        <AlertDescription className="space-y-3">
          {friendlyLiveError(session.error)}
          <Button asChild variant="outline" size="sm">
            <Link to="/live">Về danh sách phiên</Link>
          </Button>
        </AlertDescription>
      </Alert>
    )
  }
  const state = session.data
  const youtubeChatEnded = [
    "chat_disabled_or_ended",
    "chat_disabled",
    "broadcast_ended",
    "chat_not_found",
  ].includes(state.youtube_ingest_status)
  return (
    <div className="space-y-5">
      <Button asChild variant="ghost" size="sm">
        <Link to="/live">← Tất cả phiên live</Link>
      </Button>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-3xl font-semibold">Live Control Room</h1>
          <p className="text-muted-foreground">
            {sessionModeLabel(state)} · Phiên {sessionId.slice(0, 8)} · audio
            chỉ phát ở overlay.
          </p>
        </div>
        {(state.mode === "mock" || state.voice_mode === "mock") && (
          <MockBadge
            label={
              state.mode === "mock" && state.voice_mode === "real"
                ? "EVENTS MOCK · AI REAL"
                : state.mode === "youtube"
                  ? "YOUTUBE REAL · AI MOCK"
                  : undefined
            }
          />
        )}
      </div>
      <div
        className="flex flex-wrap gap-2"
        aria-label="Trạng thái phiên"
        role="status"
      >
        <Badge variant={state.status === "active" ? "default" : "secondary"}>
          {sessionStatusLabel(state.status)}
        </Badge>
        <Badge variant={connected ? "default" : "destructive"}>
          Dashboard WS {connected ? "online" : "offline"}
        </Badge>
        <Badge variant={overlayConnected ? "default" : "secondary"}>
          OBS {overlayConnected ? "connected" : "waiting"}
        </Badge>
        {state.voice_mode === "real" && (
          <Badge variant={sttConnected ? "default" : "destructive"}>
            Deepgram {sttConnected ? "connected" : "waiting"}
          </Badge>
        )}
        <Badge variant={state.ai_muted ? "destructive" : "secondary"}>
          {state.ai_muted ? "Đã tắt tiếng" : "AI có tiếng"}
        </Badge>
        <Badge variant="outline">
          {state.voice_mode === "real"
            ? `Silero · Deepgram · ${
                character.data?.llm_provider === "openai"
                  ? "OpenAI"
                  : "FPT Marketplace"
              } · ${
                character.data?.voice_provider === "google_chirp"
                  ? "Chirp 3 HD"
                  : character.data?.voice_provider === "edge"
                    ? "Edge TTS thử nghiệm"
                    : "gTTS tiếng Việt"
              }`
            : "Fake STT · LLM · TTS"}
        </Badge>
        {state.mode === "youtube" && (
          <Badge
            variant={
              state.youtube_ingest_status === "connected"
                ? "default"
                : "destructive"
            }
          >
            YouTube: {youtubeStatusLabel(state.youtube_ingest_status)}
          </Badge>
        )}
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Điều khiển phiên</CardTitle>
          <CardDescription>
            Mute tắt tiếng ngay nhưng giữ phiên. Stop kết thúc vĩnh viễn, hủy
            audio và vô hiệu hóa overlay URL cũ.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap gap-2">
            {state.status === "draft" && (
              <Button
                disabled={control.isPending}
                onClick={() => control.mutate("start")}
              >
                <Play /> Start
              </Button>
            )}
            {state.status === "paused" && (
              <Button
                disabled={control.isPending}
                onClick={() => control.mutate("resume")}
              >
                <Play /> Resume
              </Button>
            )}
            {state.status === "active" && (
              <Button
                disabled={control.isPending}
                variant="outline"
                onClick={() => control.mutate("pause")}
              >
                <Pause /> Pause
              </Button>
            )}
            {state.status === "active" && (
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="outline"
                  disabled={avatarMotion.isPending || !overlayConnected}
                  onClick={() =>
                    avatarMotion.mutate({ motion: "greet", durationSeconds: 8 })
                  }
                >
                  Vẫy tay chào
                </Button>
                <Button
                  variant="outline"
                  disabled={avatarMotion.isPending || !overlayConnected}
                  onClick={() =>
                    avatarMotion.mutate({ motion: "heart", durationSeconds: 8 })
                  }
                >
                  Tạo hình trái tim
                </Button>
                <Button
                  variant="outline"
                  disabled={avatarMotion.isPending || !overlayConnected}
                  onClick={() =>
                    avatarMotion.mutate({
                      motion: activeMotion === "dance" ? "idle" : "dance",
                      durationSeconds: activeMotion === "dance" ? 0 : 150,
                    })
                  }
                >
                  {activeMotion === "dance"
                    ? "Dừng dance"
                    : "Dance 2 Phút Hơn (local)"}
                </Button>
              </div>
            )}
            {!state.ai_muted && state.status !== "stopped" && (
              <Button
                variant="destructive"
                disabled={control.isPending}
                onClick={() => control.mutate("mute")}
              >
                <VolumeX /> Mute
              </Button>
            )}
            {state.ai_muted && state.status === "active" && (
              <Button
                disabled={control.isPending}
                variant="outline"
                onClick={() => control.mutate("unmute")}
              >
                <Volume2 /> Unmute
              </Button>
            )}
            {state.status !== "stopped" && (
              <Button
                variant="destructive"
                disabled={control.isPending}
                onClick={() => setConfirmStop(true)}
              >
                <Square /> Stop
              </Button>
            )}
          </div>
          {confirmStop && (
            <Alert variant="destructive">
              <AlertTitle>Kết thúc phiên này?</AlertTitle>
              <AlertDescription className="space-y-3">
                Audio sẽ dừng ngay, overlay URL hiện tại hết hiệu lực và phiên
                này không thể Start lại. Phiên mới sẽ cần một URL OBS mới.
                <div className="flex flex-wrap gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setConfirmStop(false)}
                  >
                    Giữ phiên
                  </Button>
                  <Button
                    variant="destructive"
                    size="sm"
                    disabled={control.isPending}
                    onClick={() => control.mutate("stop")}
                  >
                    Xác nhận Stop
                  </Button>
                </div>
              </AlertDescription>
            </Alert>
          )}
          {error && (
            <Alert variant="destructive">
              <AlertTitle>Thao tác chưa hoàn tất</AlertTitle>
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}
        </CardContent>
      </Card>
      {state.voice_mode === "real" && (
        <Card>
          <CardHeader>
            <CardTitle>Microphone AI thời gian thực</CardTitle>
            <CardDescription>
              Mic chỉ gửi PCM16 khi Silero phát hiện giọng nói. Dashboard không
              phát audio AI; hãy dùng tai nghe để tránh phản hồi âm thanh.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex flex-wrap items-center gap-3">
              {mic.state === "off" || mic.state === "error" ? (
                <Button
                  onClick={() => mic.start()}
                  disabled={!connected || state.status !== "active"}
                >
                  <Mic /> Bật microphone
                </Button>
              ) : (
                <Button variant="destructive" onClick={() => mic.stop()}>
                  <Mic /> Tắt microphone
                </Button>
              )}
              <Badge
                variant={mic.state === "error" ? "destructive" : "outline"}
              >
                {mic.state}
              </Badge>
              <div className="h-2 w-36 overflow-hidden rounded bg-muted">
                <div
                  className="h-full bg-primary transition-[width]"
                  style={{ width: `${Math.round(mic.level * 100)}%` }}
                />
              </div>
            </div>
            {mic.error && (
              <p className="text-sm text-destructive">{mic.error}</p>
            )}
          </CardContent>
        </Card>
      )}
      {state.mode === "youtube" && (
        <Card>
          <CardHeader>
            <CardTitle>Chat của livestream YouTube</CardTitle>
            <CardDescription>
              {youtubeChatEnded
                ? "Chat cũ đã kết thúc hoặc bị tắt. Bạn có thể gắn video đang live khác vào chính phiên này; mic và OBS overlay vẫn giữ nguyên."
                : ["ready", "connecting", "connected"].includes(
                      state.youtube_ingest_status,
                    )
                  ? "Chỉ chat của video gắn bên dưới được đọc. Trạng thái được cập nhật tự động."
                  : friendlyLiveError(
                      new Error(
                        state.youtube_last_error ?? state.youtube_ingest_status,
                      ),
                    )}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm">
              Video đang gắn:{" "}
              {state.youtube_broadcast_id ? (
                <a
                  href={`https://www.youtube.com/watch?v=${encodeURIComponent(state.youtube_broadcast_id)}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-primary underline"
                >
                  Xem trên YouTube <ExternalLink className="size-3" />
                </a>
              ) : (
                "Chưa có"
              )}
              {state.youtube_broadcast_id && (
                <span className="text-muted-foreground">
                  {" "}
                  · {state.youtube_broadcast_id}
                </span>
              )}
            </p>
            {!youtubeChatEnded &&
              state.status === "active" &&
              !["ready", "connecting", "connected"].includes(
                state.youtube_ingest_status,
              ) && (
                <Button
                  variant="outline"
                  disabled={reconnect.isPending}
                  onClick={() => reconnect.mutate()}
                >
                  <RefreshCw /> Kết nối ingest lại
                </Button>
              )}
            {state.status !== "stopped" && (
              <div className="space-y-2 rounded-xl border p-3">
                <strong className="text-sm">
                  Đổi sang livestream đang phát
                </strong>
                <p className="text-xs text-muted-foreground">
                  Chọn video đang phát bên dưới, hoặc dán link từ YouTube
                  Studio. Không cần Stop hay thay URL OBS.
                </p>
                <div className="space-y-2">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-medium">
                      Livestream đang phát trên kênh đã kết nối
                    </span>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      disabled={activeBroadcasts.isFetching}
                      onClick={() => void activeBroadcasts.refetch()}
                    >
                      <RefreshCw /> Tải lại
                    </Button>
                  </div>
                  {activeBroadcasts.isLoading && (
                    <p className="text-xs text-muted-foreground">
                      Đang tìm livestream…
                    </p>
                  )}
                  {activeBroadcasts.data?.map((broadcast) => (
                    <div
                      key={broadcast.id}
                      className="flex flex-wrap items-center justify-between gap-2 rounded-lg border p-2"
                    >
                      <span className="text-sm">{broadcast.title}</span>
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        onClick={() => {
                          setVideoUrl(broadcast.id)
                          setResolvedBroadcast(broadcast)
                          resolveBroadcast.reset()
                        }}
                      >
                        {broadcast.id === state.youtube_broadcast_id
                          ? "Kiểm tra lại chat"
                          : "Chọn livestream này"}
                      </Button>
                    </div>
                  ))}
                  {activeBroadcasts.isSuccess &&
                    !activeBroadcasts.data.length && (
                      <p className="text-xs text-muted-foreground">
                        YouTube chưa trả livestream đang phát cho kênh này. Kiểm
                        tra kênh Google hoặc dán link video bên dưới.
                      </p>
                    )}
                  {activeBroadcasts.error && (
                    <p className="text-xs text-destructive">
                      Không tải được danh sách:{" "}
                      {friendlyLiveError(activeBroadcasts.error)}
                    </p>
                  )}
                </div>
                <div className="flex flex-wrap gap-2">
                  <Input
                    aria-label="Liên kết livestream mới"
                    placeholder="https://youtube.com/live/..."
                    value={videoUrl}
                    onChange={(event) => {
                      setVideoUrl(event.target.value)
                      setResolvedBroadcast(null)
                    }}
                    className="min-w-64 flex-1"
                  />
                  <Button
                    type="button"
                    variant="outline"
                    disabled={!videoUrl.trim() || resolveBroadcast.isPending}
                    onClick={() => resolveBroadcast.mutate()}
                  >
                    Kiểm tra link
                  </Button>
                </div>
                {resolveBroadcast.error && (
                  <p role="alert" className="text-sm text-destructive">
                    {friendlyLiveError(resolveBroadcast.error)}
                  </p>
                )}
                {resolvedBroadcast && (
                  <div className="space-y-2 rounded-lg bg-muted p-3 text-sm">
                    <p>
                      Đã xác minh: <strong>{resolvedBroadcast.title}</strong> ·
                      live chat khả dụng.
                    </p>
                    <Button
                      type="button"
                      disabled={
                        bindBroadcast.isPending ||
                        (resolvedBroadcast.id === state.youtube_broadcast_id &&
                          resolvedBroadcast.live_chat_id ===
                            state.youtube_live_chat_id &&
                          state.youtube_ingest_status === "connected")
                      }
                      onClick={() => bindBroadcast.mutate()}
                    >
                      Gắn chat của video này vào phiên
                    </Button>
                  </div>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      )}
      <div className="grid gap-5 xl:grid-cols-[1.15fr_.85fr]">
        <div className="space-y-5">
          <Card>
            <CardHeader>
              <CardTitle>OBS Browser Overlay</CardTitle>
              <CardDescription>
                Thêm URL này vào OBS Browser Source 1280×720. Đừng hiển thị URL
                token trên stream.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {state.status === "stopped" ? (
                <Alert>
                  <AlertTitle>Overlay của phiên này đã đóng</AlertTitle>
                  <AlertDescription>
                    Tạo phiên mới để lấy overlay URL mới. Không dùng lại URL của
                    phiên đã kết thúc.
                  </AlertDescription>
                </Alert>
              ) : overlayUrl ? (
                <>
                  <Input
                    readOnly
                    type="password"
                    value={overlayUrl}
                    aria-label="Overlay URL bí mật"
                  />
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      onClick={() => navigator.clipboard.writeText(overlayUrl)}
                    >
                      <Copy /> Copy URL
                    </Button>
                    <Button asChild variant="outline">
                      <a href={overlayUrl} target="_blank" rel="noreferrer">
                        <ExternalLink /> Mở preview
                      </a>
                    </Button>
                  </div>
                </>
              ) : (
                <Button onClick={() => rotate.mutate()}>
                  Tạo URL overlay mới
                </Button>
              )}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Simulator</CardTitle>
              <CardDescription>
                {state.mode === "youtube"
                  ? "Transcript vẫn mock ở Phase 2; chat và donate đến từ YouTube thật."
                  : "Transcript, chat và donate đều đi qua cùng contract/Director."}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-5">
              <div className="space-y-2">
                <Label htmlFor="transcript">Streamer transcript</Label>
                <div className="flex gap-2">
                  <Input
                    id="transcript"
                    value={transcript}
                    onChange={(e) => setTranscript(e.target.value)}
                  />
                  <Button
                    disabled={state.status !== "active"}
                    onClick={() =>
                      send("streamer.transcript.final", {
                        turn_id: crypto.randomUUID(),
                        text: transcript,
                        confidence: 0.99,
                      })
                    }
                  >
                    <Mic /> Inject
                  </Button>
                </div>
              </div>
              {state.mode === "mock" && (
                <>
                  <div className="space-y-2">
                    <Label htmlFor="viewer-chat">YouTube chat mock</Label>
                    <div className="flex gap-2">
                      <Input
                        id="viewer-chat"
                        value={viewerText}
                        onChange={(e) => setViewerText(e.target.value)}
                      />
                      <Button
                        variant="outline"
                        disabled={state.status !== "active"}
                        onClick={() =>
                          send("youtube.chat.message", {
                            provider_message_id: crypto.randomUUID(),
                            author_channel_id: "mock-channel",
                            author_name: "Viewer",
                            text: viewerText,
                          })
                        }
                      >
                        Chat
                      </Button>
                    </div>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="donor">Super Chat mock</Label>
                    <div className="flex gap-2">
                      <Input
                        id="donor"
                        value={donor}
                        onChange={(e) => setDonor(e.target.value)}
                      />
                      <Button
                        variant="outline"
                        disabled={state.status !== "active"}
                        onClick={() =>
                          send("youtube.superchat", {
                            provider_message_id: crypto.randomUUID(),
                            author_name: donor,
                            text: "Cố lên!",
                            amount_micros: 50000000000,
                            currency: "VND",
                          })
                        }
                      >
                        Donate
                      </Button>
                    </div>
                  </div>
                </>
              )}
              {lastDecision && (
                <p className="rounded-md bg-muted p-3 text-sm">
                  Director: {lastDecision}
                </p>
              )}
            </CardContent>
          </Card>
        </div>
        <div className="space-y-5">
          <Card>
            <CardHeader>
              <CardTitle>Event timeline</CardTitle>
              <CardDescription>
                Không hiển thị prompt nội bộ hoặc secrets.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div
                className="max-h-[460px] space-y-2 overflow-auto"
                data-testid="event-timeline"
              >
                {events.length ? (
                  events.map((event) => (
                    <div
                      key={event.event_id}
                      className="rounded-lg border p-3 text-sm"
                    >
                      <div className="flex justify-between gap-3">
                        <strong>{event.type}</strong>
                        <span className="text-xs text-muted-foreground">
                          {new Date(event.ts).toLocaleTimeString()}
                        </span>
                      </div>
                      {event.type === "director.decision" && (
                        <p className="text-muted-foreground">
                          {String(event.payload.decision)} ·{" "}
                          {String(event.payload.reason_code)}
                        </p>
                      )}
                      {event.type === "speech.start" && (
                        <p className="line-clamp-2 text-muted-foreground">
                          {String(event.payload.text)}
                        </p>
                      )}
                      {event.type === "streamer.transcript.final" && (
                        <p className="line-clamp-2 text-muted-foreground">
                          {String(event.payload.text ?? "")}
                        </p>
                      )}
                    </div>
                  ))
                ) : (
                  <p className="text-muted-foreground">Chưa có event.</p>
                )}
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Usage & telemetry</CardTitle>
              <CardDescription>
                {state.voice_mode === "real"
                  ? "Đo cục bộ trên phiên provider; kết quả chỉ có ý nghĩa khi credentials thật đang hoạt động."
                  : "Local simulated measurements, not real-provider performance."}
              </CardDescription>
            </CardHeader>
            <CardContent
              className="grid grid-cols-2 gap-3 text-sm"
              data-testid="mock-telemetry"
            >
              <div>
                LLM output tokens
                <strong className="block text-xl">
                  {usage.data?.llm_output_tokens ?? 0}
                </strong>
              </div>
              <div>
                TTS characters
                <strong className="block text-xl">
                  {usage.data?.tts_characters ?? 0}
                </strong>
              </div>
              <div>
                Chi phí ước tính
                <strong className="block text-xl">
                  {usage.data?.estimated_usd == null
                    ? "Chưa cấu hình"
                    : `$${usage.data.estimated_usd.toFixed(4)}`}
                </strong>
              </div>
              <div>
                STT seconds
                <strong className="block text-xl">
                  {usage.data?.stt_seconds ?? 0}
                </strong>
              </div>
              <div>
                Provider errors
                <strong className="block text-xl">
                  {usage.data?.provider_errors ?? 0}
                </strong>
              </div>
              <div>
                Reconnect overlay
                <strong className="block text-xl">
                  {usage.data?.overlay_reconnect_count ?? 0}
                </strong>
              </div>
              <div>
                Event to decision P95
                <strong className="block text-xl">
                  {usage.data?.telemetry.metrics.event_to_decision_ms?.p95_ms ??
                    "—"}
                  {usage.data?.telemetry.metrics.event_to_decision_ms && " ms"}
                </strong>
              </div>
              <div>
                Event to playback P95
                <strong className="block text-xl">
                  {usage.data?.telemetry.metrics.event_to_first_playback_ack_ms
                    ?.p95_ms ?? "—"}
                  {usage.data?.telemetry.metrics
                    .event_to_first_playback_ack_ms && " ms"}
                </strong>
              </div>
              <p className="col-span-2 text-xs text-muted-foreground">
                Scope:{" "}
                {usage.data?.telemetry.measurement_scope ??
                  "MOCK_SIMULATED_LOCAL"}
              </p>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
