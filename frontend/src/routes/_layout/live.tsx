import { useMutation, useQuery } from "@tanstack/react-query"
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router"
import {
  ArrowRight,
  Clock3,
  Mic,
  Radio,
  RefreshCw,
  Tv,
  Video,
} from "lucide-react"
import { useState } from "react"

import { MockBadge } from "@/components/Live/MockBadge"
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
import { liveApi, type YouTubeBroadcast } from "@/lib/liveApi"
import {
  friendlyLiveError,
  sessionModeLabel,
  sessionStatusLabel,
  youtubeStatusLabel,
} from "@/lib/liveUi"

export const Route = createFileRoute("/_layout/live")({ component: LiveSetup })

function LiveSetup() {
  const navigate = useNavigate()
  const characters = useQuery({
    queryKey: ["characters"],
    queryFn: liveApi.listCharacters,
  })
  const currentSession = useQuery({
    queryKey: ["current-live-session"],
    queryFn: liveApi.currentSession,
    refetchInterval: 10_000,
  })
  const sessions = useQuery({
    queryKey: ["live-sessions"],
    queryFn: liveApi.listSessions,
  })
  const [selected, setSelected] = useState("")
  const [mode, setMode] = useState<"mock" | "youtube">("mock")
  const [voiceMode, setVoiceMode] = useState<"mock" | "real">("mock")
  const [broadcastId, setBroadcastId] = useState("")
  const [videoUrl, setVideoUrl] = useState("")
  const [manualBroadcast, setManualBroadcast] =
    useState<YouTubeBroadcast | null>(null)
  const youtube = useQuery({
    queryKey: ["youtube-connection"],
    queryFn: liveApi.youtubeConnection,
  })
  const broadcasts = useQuery({
    queryKey: ["youtube-broadcasts"],
    queryFn: liveApi.youtubeBroadcasts,
    enabled: youtube.data?.connected === true,
  })
  const resolveBroadcast = useMutation({
    mutationFn: () => liveApi.resolveYoutubeBroadcast(videoUrl),
    onSuccess: (broadcast) => {
      setManualBroadcast(broadcast)
      setBroadcastId(broadcast.id)
    },
  })
  const create = useMutation({
    mutationFn: () =>
      liveApi.createSession(
        selected,
        mode,
        broadcastId || undefined,
        voiceMode,
      ),
    onSuccess: (session) => {
      if (session.overlay_url)
        sessionStorage.setItem(`overlay:${session.id}`, session.overlay_url)
      navigate({ to: "/live/$sessionId", params: { sessionId: session.id } })
    },
    onError: () => {
      void currentSession.refetch()
      void sessions.refetch()
    },
  })
  const runningSession = currentSession.data
  const recentSessions = sessions.data
    ?.filter((session) => session.id !== runningSession?.id)
    .slice(0, 6)
  const selectedCharacter = characters.data?.data.find(
    (character) => character.id === selected,
  )
  const canCreate =
    Boolean(selectedCharacter) &&
    currentSession.isSuccess &&
    !runningSession &&
    !create.isPending &&
    (mode === "mock" || Boolean(broadcastId))
  return (
    <div className="space-y-6">
      <div className="rounded-3xl border bg-gradient-to-br from-primary/10 via-background to-background p-6 md:p-8">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <Badge variant="outline">LIVE WORKSPACE</Badge>
          <MockBadge label="Có chế độ Demo" />
        </div>
        <div>
          <h1 className="text-3xl font-semibold tracking-tight md:text-4xl">
            Quản lý phiên live
          </h1>
          <p className="mt-2 max-w-2xl text-muted-foreground">
            Một tài khoản chỉ chạy một phiên tại một thời điểm. Mở lại phiên
            hiện tại, tiếp tục bản nháp hoặc tạo phiên mới theo các bước bên
            dưới.
          </p>
        </div>
      </div>
      {runningSession && (
        <Card
          className="border-primary/40 bg-primary/5"
          data-testid="current-session"
        >
          <CardHeader>
            <div className="flex flex-wrap items-center gap-2">
              <CardTitle>
                {runningSession.status === "active"
                  ? "Phiên live đang chạy"
                  : "Phiên live đang tạm dừng"}
              </CardTitle>
              <Badge>{sessionStatusLabel(runningSession.status)}</Badge>
            </div>
            <CardDescription>
              {sessionModeLabel(runningSession)} · Mã phiên{" "}
              {runningSession.id.slice(0, 8)}
            </CardDescription>
            {runningSession.mode === "youtube" && (
              <Badge
                variant={
                  runningSession.youtube_ingest_status === "connected"
                    ? "default"
                    : "destructive"
                }
              >
                YouTube:{" "}
                {youtubeStatusLabel(runningSession.youtube_ingest_status)}
              </Badge>
            )}
          </CardHeader>
          <CardContent className="space-y-3">
            {runningSession.mode === "youtube" &&
              [
                "chat_disabled_or_ended",
                "chat_disabled",
                "broadcast_ended",
                "chat_not_found",
              ].includes(runningSession.youtube_ingest_status) && (
                <Alert variant="destructive">
                  <AlertTitle>Chat của phiên này không còn khả dụng</AlertTitle>
                  <AlertDescription>
                    Nếu đã mở livestream khác, hãy mở phiên này và chọn Stop.
                    Sau đó tạo phiên mới với broadcast đang phát; không cần kết
                    nối lại Google.
                  </AlertDescription>
                </Alert>
              )}
            <p className="text-sm text-muted-foreground">
              Tạo phiên mới sẽ được mở khóa sau khi bạn chủ động Stop phiên hiện
              tại. Thao tác Stop sẽ ngắt audio và vô hiệu hóa overlay URL cũ.
            </p>
            <Button
              type="button"
              onClick={() =>
                navigate({
                  to: "/live/$sessionId",
                  params: { sessionId: runningSession.id },
                })
              }
            >
              Mở phiên đang chạy
            </Button>
          </CardContent>
        </Card>
      )}
      {currentSession.error && (
        <Alert variant="destructive">
          <AlertTitle>Chưa kiểm tra được phiên đang chạy</AlertTitle>
          <AlertDescription>
            {friendlyLiveError(currentSession.error)} Nếu backend vừa cập nhật,
            hãy tải lại trang trước khi tạo phiên mới.
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="mt-2 block"
              onClick={() => void currentSession.refetch()}
              disabled={currentSession.isFetching}
            >
              Kiểm tra lại
            </Button>
          </AlertDescription>
        </Alert>
      )}
      <Card data-testid="recent-sessions">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Clock3 className="size-5" /> Phiên gần đây
          </CardTitle>
          <CardDescription>
            Bản nháp có thể mở lại; phiên đã kết thúc chỉ để xem thông tin,
            không phát lại audio hay overlay cũ.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          {sessions.isLoading && (
            <p className="text-sm text-muted-foreground">Đang tải phiên…</p>
          )}
          {sessions.error && (
            <p className="text-sm text-destructive">
              Chưa tải được lịch sử phiên. Bạn vẫn có thể dùng phiên đang mở.
            </p>
          )}
          {sessions.isSuccess && !recentSessions?.length && (
            <p className="text-sm text-muted-foreground">
              Chưa có phiên cũ. Hãy tạo phiên đầu tiên bên dưới.
            </p>
          )}
          {recentSessions?.map((session) => (
            <div
              key={session.id}
              className="flex flex-wrap items-center justify-between gap-3 rounded-xl border p-3"
            >
              <div className="space-y-1">
                <div className="flex flex-wrap items-center gap-2">
                  <strong>
                    {characters.data?.data.find(
                      (item) => item.id === session.character_id,
                    )?.name ?? "Nhân vật"}
                  </strong>
                  <Badge
                    variant={
                      session.status === "draft" ? "outline" : "secondary"
                    }
                  >
                    {sessionStatusLabel(session.status)}
                  </Badge>
                </div>
                <p className="text-xs text-muted-foreground">
                  {sessionModeLabel(session)} ·{" "}
                  {new Date(session.created_at).toLocaleString("vi-VN", {
                    dateStyle: "short",
                    timeStyle: "short",
                  })}{" "}
                  · {session.id.slice(0, 8)}
                </p>
              </div>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() =>
                  navigate({
                    to: "/live/$sessionId",
                    params: { sessionId: session.id },
                  })
                }
              >
                {session.status === "draft"
                  ? "Tiếp tục thiết lập"
                  : "Xem phiên"}
                <ArrowRight />
              </Button>
            </div>
          ))}
        </CardContent>
      </Card>
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-2xl font-semibold">Tạo phiên mới</h2>
          <p className="text-sm text-muted-foreground">
            Chọn nguồn, giọng nói và nhân vật trước khi tạo bản nháp.
          </p>
        </div>
        {runningSession && (
          <Badge variant="secondary">Đang khóa: có phiên chạy</Badge>
        )}
      </div>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Badge variant="outline">1</Badge> <Tv className="size-5" /> Nguồn
            sự kiện
          </CardTitle>
          <CardDescription>
            Chọn Demo để tập trước, hoặc YouTube Live để đọc chat và sự kiện ủng
            hộ từ livestream thật. Ứng dụng không gửi tin nhắn lên YouTube.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              variant={mode === "mock" ? "default" : "outline"}
              aria-pressed={mode === "mock"}
              onClick={() => {
                setMode("mock")
                setBroadcastId("")
                setManualBroadcast(null)
              }}
            >
              Demo / Mock
            </Button>
            <Button
              type="button"
              variant={mode === "youtube" ? "default" : "outline"}
              disabled={!youtube.data?.connected}
              aria-pressed={mode === "youtube"}
              onClick={() => setMode("youtube")}
            >
              YouTube thật
            </Button>
          </div>
          <p className="text-sm text-muted-foreground">
            {mode === "mock"
              ? "Dữ liệu chat/ủng hộ được mô phỏng. Không kết nối livestream thật."
              : "Chỉ các livestream đang phát có chat khả dụng mới được chọn."}
          </p>
          {mode === "youtube" && (
            <div className="grid gap-2">
              <p className="text-sm text-muted-foreground">
                Kênh đã kết nối:{" "}
                <strong>{youtube.data?.channel_name || "Chưa xác định"}</strong>
                . Chỉ chọn video thuộc đúng kênh này.
              </p>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <strong className="text-sm">Livestream đang phát</strong>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => void broadcasts.refetch()}
                  disabled={broadcasts.isFetching}
                >
                  <RefreshCw /> Tải lại danh sách
                </Button>
              </div>
              {broadcasts.isLoading && (
                <p className="text-sm text-muted-foreground">
                  Đang tìm livestream trên kênh đã kết nối…
                </p>
              )}
              {broadcasts.data?.map((broadcast) => (
                <button
                  type="button"
                  key={broadcast.id}
                  onClick={() => setBroadcastId(broadcast.id)}
                  aria-pressed={broadcastId === broadcast.id}
                  className={`rounded-xl border p-3 text-left transition-colors ${broadcastId === broadcast.id ? "border-primary bg-primary/10" : "hover:bg-muted"}`}
                >
                  <strong>{broadcast.title}</strong>
                  <Badge variant="secondary" className="ml-2">
                    Đang phát
                  </Badge>
                </button>
              ))}
              {broadcasts.isSuccess && !broadcasts.data.length && (
                <Alert>
                  <AlertTitle>Chưa có livestream đang phát</AlertTitle>
                  <AlertDescription>
                    Bắt đầu phát trực tiếp trên kênh YouTube đã kết nối, bật
                    live chat rồi chọn “Tải lại danh sách”. Nếu YouTube Studio
                    đang hiện video live nhưng danh sách vẫn trống, dán liên kết
                    video bên dưới để kiểm tra trực tiếp.
                  </AlertDescription>
                </Alert>
              )}
              {broadcasts.error && (
                <Alert variant="destructive">
                  <AlertTitle>Không tải được livestream</AlertTitle>
                  <AlertDescription>
                    {friendlyLiveError(broadcasts.error)}
                  </AlertDescription>
                </Alert>
              )}
              <div className="space-y-2 rounded-xl border p-3">
                <strong className="text-sm">Không thấy luồng của bạn?</strong>
                <p className="text-xs text-muted-foreground">
                  Dán link video đang phát từ YouTube Studio. Kira sẽ kiểm tra
                  video thuộc kênh đã kết nối và có live chat trước khi gắn.
                </p>
                <div className="flex flex-wrap gap-2">
                  <Input
                    aria-label="Liên kết livestream YouTube"
                    placeholder="https://youtube.com/live/..."
                    value={videoUrl}
                    onChange={(event) => {
                      setVideoUrl(event.target.value)
                      if (manualBroadcast?.id === broadcastId)
                        setBroadcastId("")
                      setManualBroadcast(null)
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
                {manualBroadcast && (
                  <p className="text-sm text-primary">
                    Đã xác minh: {manualBroadcast.title} · live chat khả dụng.
                  </p>
                )}
                {resolveBroadcast.error && (
                  <p role="alert" className="text-sm text-destructive">
                    {friendlyLiveError(resolveBroadcast.error)}
                  </p>
                )}
              </div>
            </div>
          )}
          {youtube.isSuccess && !youtube.data.connected && (
            <div className="flex flex-wrap items-center gap-3 rounded-xl bg-muted/60 p-3 text-sm">
              <span>Muốn dùng YouTube Live? Kết nối kênh trước.</span>
              <Button asChild size="sm" variant="outline">
                <Link to="/settings/connections">Mở kết nối YouTube</Link>
              </Button>
            </div>
          )}
          {youtube.error && (
            <p className="text-sm text-destructive">
              Không kiểm tra được kết nối YouTube.{" "}
              {friendlyLiveError(youtube.error)}
            </p>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Badge variant="outline">2</Badge> <Mic className="size-5" /> Giọng
            nói AI
          </CardTitle>
          <CardDescription>
            Chế độ này độc lập với nguồn sự kiện. YouTube thật vẫn có thể dùng
            giọng mô phỏng để thử an toàn.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant={voiceMode === "mock" ? "default" : "outline"}
            aria-pressed={voiceMode === "mock"}
            onClick={() => setVoiceMode("mock")}
          >
            Voice Mock
          </Button>
          <Button
            type="button"
            variant={voiceMode === "real" ? "default" : "outline"}
            aria-pressed={voiceMode === "real"}
            onClick={() => setVoiceMode("real")}
          >
            Voice Real
          </Button>
          <p className="w-full text-xs text-muted-foreground">
            {voiceMode === "real"
              ? "Giọng thật dùng micro → Deepgram → AI → TTS đã chọn trong Character Studio. Chỉ OBS overlay phát tiếng AI."
              : "Giọng mô phỏng dùng Fake LLM/TTS và audio demo, không gọi nhà cung cấp AI thật."}
          </p>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Badge variant="outline">3</Badge> <Video className="size-5" /> Chọn
            nhân vật
          </CardTitle>
          <CardDescription>
            OBS sẽ nhận avatar và audio; dashboard không phát audio AI.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 md:grid-cols-3">
            {characters.data?.data.map((character) => (
              <button
                type="button"
                key={character.id}
                onClick={() => setSelected(character.id)}
                aria-pressed={selected === character.id}
                className={`rounded-xl border p-4 text-left transition-colors ${selected === character.id ? "border-primary bg-primary/10" : "hover:bg-muted"}`}
              >
                <strong>{character.name}</strong>
                <p className="mt-1 text-sm text-muted-foreground">
                  {character.persona_description}
                </p>
              </button>
            ))}
          </div>
          {!characters.isLoading && !characters.data?.count && (
            <div className="flex flex-wrap items-center gap-3">
              <p>
                Chưa có nhân vật. Hãy tạo Kira trong Character Studio trước.
              </p>
              <Button asChild variant="outline" size="sm">
                <Link to="/studio">Mở Character Studio</Link>
              </Button>
            </div>
          )}
          {characters.error && (
            <p className="text-sm text-destructive">
              Không tải được nhân vật. {friendlyLiveError(characters.error)}
            </p>
          )}
        </CardContent>
      </Card>
      <Card className="border-primary/30">
        <CardHeader>
          <CardTitle>Xác nhận trước khi tạo</CardTitle>
          <CardDescription>
            Tạo phiên chỉ chuẩn bị control room. AI và YouTube bắt đầu nhận sự
            kiện khi bạn nhấn Start trong phiên đó.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-2">
            <Badge variant="outline">
              {mode === "youtube" ? "YouTube thật" : "Demo / Mock"}
            </Badge>
            <Badge variant="outline">
              {voiceMode === "real" ? "Voice Real" : "Voice Mock"}
            </Badge>
            <Badge variant="outline">
              {selectedCharacter?.name ?? "Chưa chọn nhân vật"}
            </Badge>
          </div>
          {mode === "youtube" && !broadcastId && (
            <p className="text-sm text-muted-foreground">
              Chọn một livestream đang phát ở bước 1.
            </p>
          )}
          {runningSession && (
            <p className="text-sm text-muted-foreground">
              Đang có một phiên{" "}
              {sessionStatusLabel(runningSession.status).toLowerCase()}. Hãy mở
              phiên đó và Stop trước khi tạo phiên khác.
            </p>
          )}
          <Button onClick={() => create.mutate()} disabled={!canCreate}>
            <Radio /> Tạo phiên {mode === "youtube" ? "YouTube" : "Demo"} ·
            {voiceMode === "real" ? " Voice Real" : " Voice Mock"}
          </Button>
          {create.error && (
            <Alert variant="destructive">
              <AlertTitle>Chưa tạo được phiên</AlertTitle>
              <AlertDescription>
                {friendlyLiveError(create.error)}
              </AlertDescription>
            </Alert>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
