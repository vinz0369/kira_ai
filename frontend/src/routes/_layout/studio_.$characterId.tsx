import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import { lazy, Suspense, useEffect, useRef, useState } from "react"

import { MockBadge } from "@/components/Live/MockBadge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { useLocal2PhutHonMotion, useLocalAvatarUrl } from "@/lib/avatarAssets"
import { liveApi } from "@/lib/liveApi"

const AvatarScene = lazy(() =>
  import("@/components/Live/AvatarScene").then((module) => ({
    default: module.AvatarScene,
  })),
)

export const Route = createFileRoute("/_layout/studio_/$characterId")({
  component: CharacterEditor,
})

function CharacterEditor() {
  const { characterId } = Route.useParams()
  const queryClient = useQueryClient()
  const query = useQuery({
    queryKey: ["character", characterId],
    queryFn: () => liveApi.getCharacter(characterId),
  })
  const vrmUrl = useLocalAvatarUrl(
    query.data?.avatar_asset_id,
    null,
    query.data?.name,
  )
  const voiceOptions = useQuery({
    queryKey: ["tts-voice-options"],
    queryFn: liveApi.ttsVoiceOptions,
  })
  const llmOptions = useQuery({
    queryKey: ["llm-options"],
    queryFn: liveApi.llmOptions,
  })
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const [address, setAddress] = useState("bạn")
  const [llmProvider, setLlmProvider] = useState("fpt")
  const [llmModel, setLlmModel] = useState("Saola-Small-32B")
  const [voiceProvider, setVoiceProvider] = useState("gtts")
  const [voiceId, setVoiceId] = useState("vi")
  const [previewMotion, setPreviewMotion] = useState<
    "idle" | "greet" | "heart" | "dance"
  >("idle")
  const danceMotion = useLocal2PhutHonMotion(null, previewMotion === "dance")
  const [previewMood, setPreviewMood] = useState<
    "neutral" | "happy" | "annoyed" | "surprised" | "sad" | "relaxed" | "wink"
  >("neutral")
  const [cameraFraming, setCameraFraming] = useState<"chest-up" | "full-body">(
    "chest-up",
  )
  const [cameraZoom, setCameraZoom] = useState(1)
  const previewTimer = useRef<ReturnType<typeof setTimeout> | undefined>(
    undefined,
  )
  useEffect(() => {
    if (!query.data) return
    setName(query.data.name)
    setDescription(query.data.persona_description)
    setAddress(query.data.address_streamer_as)
    setLlmProvider(query.data.llm_provider)
    setLlmModel(query.data.llm_model)
    setVoiceProvider(query.data.voice_provider)
    setVoiceId(query.data.voice_id)
    setCameraFraming(query.data.avatar_camera_framing ?? "chest-up")
    setCameraZoom(query.data.avatar_camera_zoom ?? 1)
  }, [query.data])
  useEffect(() => () => {
    if (previewTimer.current) clearTimeout(previewTimer.current)
  })
  const previewMotionFor = (motion: "idle" | "greet" | "heart" | "dance") => {
    if (previewTimer.current) clearTimeout(previewTimer.current)
    setPreviewMotion(motion)
    const duration = motion === "dance" ? 150 : motion === "idle" ? 0 : 4
    if (duration)
      previewTimer.current = setTimeout(
        () => setPreviewMotion("idle"),
        duration * 1000,
      )
  }
  const save = useMutation({
    mutationFn: () =>
      liveApi.updateCharacter(characterId, {
        name,
        persona_description: description,
        address_streamer_as: address,
        llm_provider: llmProvider,
        llm_model: llmModel,
        voice_provider: voiceProvider,
        voice_id: voiceId,
        avatar_camera_framing: cameraFraming,
        avatar_camera_zoom: cameraZoom,
      }),
    onSuccess: (data) => {
      queryClient.setQueryData(["character", characterId], data)
      queryClient.invalidateQueries({ queryKey: ["characters"] })
    },
  })
  if (!query.data) return <p>Đang tải nhân vật…</p>
  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-semibold">Chỉnh {query.data.name}</h1>
        <MockBadge />
      </div>
      <div className="grid gap-5 lg:grid-cols-[1fr_420px]">
        <Card>
          <CardHeader>
            <CardTitle>Tính cách & xưng hô</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="edit-name">Tên</Label>
              <Input
                id="edit-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-address">Gọi streamer là</Label>
              <Input
                id="edit-address"
                value={address}
                onChange={(e) => setAddress(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-persona">Mô tả persona</Label>
              <textarea
                id="edit-persona"
                className="min-h-36 w-full rounded-md border bg-transparent p-3"
                value={description}
                maxLength={1200}
                onChange={(e) => setDescription(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-llm-provider">Nhà cung cấp LLM</Label>
              <select
                id="edit-llm-provider"
                className="h-10 w-full rounded-md border bg-background px-3"
                value={llmProvider}
                onChange={(event) => {
                  const provider = event.target.value
                  const option = llmOptions.data?.find(
                    (candidate) => candidate.id === provider,
                  )
                  setLlmProvider(provider)
                  setLlmModel(option?.models[0]?.id ?? "")
                }}
              >
                {llmOptions.data?.map((option) => (
                  <option
                    key={option.id}
                    value={option.id}
                    disabled={!option.available && option.id !== llmProvider}
                  >
                    {option.label}
                    {!option.available ? " · chưa cấu hình" : ""}
                  </option>
                ))}
              </select>
              <p className="text-xs text-muted-foreground">
                {
                  llmOptions.data?.find((option) => option.id === llmProvider)
                    ?.description
                }
              </p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-llm-model">Model hội thoại</Label>
              <select
                id="edit-llm-model"
                className="h-10 w-full rounded-md border bg-background px-3"
                value={llmModel}
                onChange={(event) => setLlmModel(event.target.value)}
              >
                {llmOptions.data
                  ?.find((option) => option.id === llmProvider)
                  ?.models.map((model) => (
                    <option key={model.id} value={model.id}>
                      {model.label}
                    </option>
                  ))}
              </select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-voice-provider">Nhà cung cấp TTS</Label>
              <select
                id="edit-voice-provider"
                className="h-10 w-full rounded-md border bg-background px-3"
                value={voiceProvider}
                onChange={(event) => {
                  const provider = event.target.value
                  const option = voiceOptions.data?.find(
                    (candidate) => candidate.id === provider,
                  )
                  setVoiceProvider(provider)
                  setVoiceId(option?.voices[0]?.id ?? "")
                }}
              >
                {voiceOptions.data?.map((option) => (
                  <option
                    key={option.id}
                    value={option.id}
                    disabled={!option.available && option.id !== voiceProvider}
                  >
                    {option.label}
                    {option.experimental ? " · thử nghiệm" : ""}
                    {!option.available ? " · chưa bật" : ""}
                  </option>
                ))}
              </select>
              <p className="text-xs text-muted-foreground">
                {
                  voiceOptions.data?.find(
                    (option) => option.id === voiceProvider,
                  )?.description
                }
              </p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-voice-id">Giọng tiếng Việt</Label>
              <select
                id="edit-voice-id"
                className="h-10 w-full rounded-md border bg-background px-3"
                value={voiceId}
                onChange={(event) => setVoiceId(event.target.value)}
              >
                {voiceOptions.data
                  ?.find((option) => option.id === voiceProvider)
                  ?.voices.map((voice) => (
                    <option key={voice.id} value={voice.id}>
                      {voice.label}
                    </option>
                  ))}
              </select>
            </div>
            <p className="text-xs text-muted-foreground">
              Safety, Mute và Stop luôn nằm ngoài persona và không thể bị ghi
              đè.
            </p>
            <Button onClick={() => save.mutate()} disabled={save.isPending}>
              Lưu thay đổi
            </Button>
            {save.isSuccess && (
              <span className="ml-3 text-sm text-emerald-500">Đã lưu</span>
            )}
          </CardContent>
        </Card>
        <Card className="overflow-hidden">
          <CardHeader>
            <CardTitle>Preview 3D</CardTitle>
            <p className="text-xs text-muted-foreground">
              Arcana chỉ tải trên máy này ở chế độ development. Nếu không tải
              được, hệ thống dùng nhân vật dự phòng. Chưa được phép phân phối
              hoặc dùng thương mại model Arcana.
            </p>
          </CardHeader>
          <CardContent className="space-y-3 bg-gradient-to-b from-primary/10 to-transparent p-3">
            <div className="flex flex-wrap items-center gap-2">
              <Label htmlFor="avatar-framing">Góc mặc định</Label>
              <select
                id="avatar-framing"
                className="h-9 rounded-md border bg-background px-2 text-sm"
                value={cameraFraming}
                onChange={(event) =>
                  setCameraFraming(
                    event.target.value as "chest-up" | "full-body",
                  )
                }
              >
                <option value="chest-up">Từ ngực lên</option>
                <option value="full-body">Toàn thân</option>
              </select>
              <Label htmlFor="avatar-zoom">Thu phóng</Label>
              <input
                id="avatar-zoom"
                aria-label="Thu phóng avatar"
                type="range"
                min="0.7"
                max="1.5"
                step="0.05"
                value={cameraZoom}
                onChange={(event) => setCameraZoom(Number(event.target.value))}
                className="min-w-24 flex-1"
              />
              <span className="w-10 text-right text-xs tabular-nums">
                {cameraZoom.toFixed(2)}×
              </span>
            </div>
            <fieldset
              className="flex flex-wrap gap-2"
              aria-label="Biểu cảm preview"
            >
              {(
                [
                  ["neutral", "Bình thường"],
                  ["happy", "Vui"],
                  ["surprised", "Ngạc nhiên"],
                  ["annoyed", "Giận"],
                  ["sad", "Buồn"],
                  ["relaxed", "Thư giãn"],
                  ["wink", "Nháy mắt"],
                ] as const
              ).map(([mood, label]) => (
                <Button
                  key={mood}
                  type="button"
                  size="sm"
                  variant={previewMood === mood ? "default" : "outline"}
                  onClick={() => setPreviewMood(mood)}
                >
                  {label}
                </Button>
              ))}
            </fieldset>
            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => previewMotionFor("idle")}
              >
                Tự nhiên
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => previewMotionFor("greet")}
              >
                Vẫy tay chào
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => previewMotionFor("heart")}
              >
                Tạo hình trái tim
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() =>
                  previewMotionFor(previewMotion === "dance" ? "idle" : "dance")
                }
              >
                {previewMotion === "dance"
                  ? "Dừng dance"
                  : "Dance 2 Phút Hơn (local)"}
              </Button>
            </div>
            <div className="relative h-[430px] overflow-hidden rounded-md">
              <Suspense fallback={null}>
                <AvatarScene
                  speaking={false}
                  mood={previewMood}
                  motion={previewMotion}
                  cameraFraming={cameraFraming}
                  cameraZoom={cameraZoom}
                  danceVmdUrl={danceMotion.url}
                  danceVmdState={danceMotion.state}
                  vrmUrl={vrmUrl}
                />
              </Suspense>
              {previewMotion === "heart" && (
                <div
                  aria-hidden="true"
                  className="pointer-events-none absolute inset-x-0 top-1/4 text-center text-5xl"
                >
                  💕 💗 💕
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
