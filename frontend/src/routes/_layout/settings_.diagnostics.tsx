import { useQuery } from "@tanstack/react-query"
import { createFileRoute, Link } from "@tanstack/react-router"
import {
  Activity,
  CheckCircle2,
  CircleAlert,
  Download,
  Mic,
} from "lucide-react"
import { useState } from "react"

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
import { liveApi, type SessionUsage } from "@/lib/liveApi"

export const Route = createFileRoute("/_layout/settings_/diagnostics")({
  component: Phase3DiagnosticsPage,
})

type MicResult = {
  status: "idle" | "checking" | "pass" | "warning" | "failed"
  detail: string
  peakRms?: number
}

const manualChecks = [
  "Tiếng Việt: thử giọng Bắc/Trung/Nam và so transcript với câu đã nói.",
  "Gaming slang: “Kira, combat này team mình outplay hay feed vậy?”",
  "Personality: hỏi cùng một chủ đề 3 lần, kiểm tra cách xưng hô và giới hạn persona.",
  "Barge-in: nói khi AI đang phát; audio cũ phải dừng và không quay lại.",
  "Mute/Stop: bấm giữa câu; OBS phải im ngay và không phát phần còn lại.",
  "Reconnect: reload Browser Source; không được phát lại utterance đã hoàn tất.",
  "OBS recording: giọng AI chỉ xuất hiện một lần, nền trong suốt, miệng chuyển idle/talking.",
]

function Status({ ok, label }: { ok: boolean; label: string }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border p-3">
      <span>{label}</span>
      <Badge variant={ok ? "default" : "destructive"}>
        {ok ? "Sẵn sàng" : "Chưa sẵn sàng"}
      </Badge>
    </div>
  )
}

function Phase3DiagnosticsPage() {
  const diagnostics = useQuery({
    queryKey: ["phase3-diagnostics"],
    queryFn: liveApi.phase3Diagnostics,
  })
  const [mic, setMic] = useState<MicResult>({
    status: "idle",
    detail: "Chưa kiểm tra. Audio chỉ được phân tích trong trình duyệt.",
  })
  const [sessionId, setSessionId] = useState("")
  const [usage, setUsage] = useState<SessionUsage | null>(null)
  const [usageError, setUsageError] = useState("")
  const [checked, setChecked] = useState<boolean[]>(
    manualChecks.map(() => false),
  )

  const browserReady =
    window.isSecureContext &&
    Boolean(navigator.mediaDevices?.getUserMedia) &&
    "AudioWorkletNode" in window &&
    "WebSocket" in window

  async function testMic() {
    setMic({ status: "checking", detail: "Đang xin quyền và đo mức mic…" })
    let stream: MediaStream | undefined
    let context: AudioContext | undefined
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      })
      context = new AudioContext()
      const source = context.createMediaStreamSource(stream)
      const analyser = context.createAnalyser()
      analyser.fftSize = 1024
      source.connect(analyser)
      const samples = new Float32Array(analyser.fftSize)
      let peakRms = 0
      for (let index = 0; index < 12; index++) {
        await new Promise((resolve) => window.setTimeout(resolve, 75))
        analyser.getFloatTimeDomainData(samples)
        const rms = Math.sqrt(
          samples.reduce((sum, value) => sum + value * value, 0) /
            samples.length,
        )
        peakRms = Math.max(peakRms, rms)
      }
      const label = stream.getAudioTracks()[0]?.label || "microphone"
      setMic({
        status: peakRms > 0.003 ? "pass" : "warning",
        detail:
          peakRms > 0.003
            ? `Đã nhận tín hiệu từ ${label}. Không upload hoặc lưu audio.`
            : `Đã có quyền ${label}, nhưng chưa thấy tín hiệu rõ. Hãy nói gần mic rồi thử lại.`,
        peakRms: Number(peakRms.toFixed(4)),
      })
    } catch (error) {
      setMic({
        status: "failed",
        detail:
          error instanceof Error
            ? error.message
            : "Không thể truy cập microphone.",
      })
    } finally {
      stream?.getTracks().forEach((track) => {
        track.stop()
      })
      await context?.close()
    }
  }

  async function loadUsage() {
    setUsageError("")
    try {
      setUsage(await liveApi.usage(sessionId.trim()))
    } catch (error) {
      setUsage(null)
      setUsageError(
        error instanceof Error ? error.message : "Không đọc được phiên",
      )
    }
  }

  function exportEvidence() {
    const evidence = {
      exported_at: new Date().toISOString(),
      label: "OPERATOR_RECORDED_DIAGNOSTIC",
      server_preflight: diagnostics.data,
      browser: { secure_context: window.isSecureContext, ready: browserReady },
      microphone: mic,
      manual_checks: manualChecks.map((label, index) => ({
        label,
        confirmed_by_operator: checked[index],
      })),
      session_usage: usage,
    }
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(evidence, null, 2)], {
        type: "application/json",
      }),
    )
    const link = document.createElement("a")
    link.href = url
    link.download = `phase3-diagnostic-${Date.now()}.json`
    link.click()
    URL.revokeObjectURL(url)
  }

  const data = diagnostics.data
  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div>
        <h1 className="flex items-center gap-2 text-3xl font-semibold">
          <Activity /> Phase 3 Diagnostics
        </h1>
        <p className="text-muted-foreground">
          Preflight không gọi provider và không phải bằng chứng latency thật.
          Chỉ phiên Voice Real có playback ACK từ overlay mới tạo metric real.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>1. Backend providers</CardTitle>
          <CardDescription>
            API chỉ trả trạng thái và model ID; không trả key, token hoặc đường
            dẫn credential.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-2">
          <Status
            ok={data?.deepgram.configured === true}
            label={`Deepgram · ${data?.deepgram.model ?? "…"}`}
          />
          <Status
            ok={data?.fpt_llm.configured === true}
            label={`FPT Marketplace · ${data?.fpt_llm.model ?? "…"}`}
          />
          <Status
            ok={data?.openai.configured === true}
            label={`OpenAI · ${data?.openai.model ?? "…"}`}
          />
          <Status
            ok={data?.google_tts.configured === true}
            label={`Google TTS · ${data?.google_tts.model ?? "…"}`}
          />
          <Status
            ok={data?.gtts.configured === true}
            label={`gTTS miễn credential · ${data?.gtts.model ?? "…"}`}
          />
          <Status
            ok={data?.edge_tts.configured === true}
            label={`Edge TTS thử nghiệm · ${data?.edge_tts.model ?? "…"}`}
          />
          <Status
            ok={data?.cost_rates_configured === true}
            label="Đơn giá cost telemetry"
          />
          <Status
            ok={data?.youtube_connected === true}
            label="YouTube OAuth + channel"
          />
          <Status
            ok={data?.real_voice_ready === true}
            label="Pipeline Voice Real"
          />
          {diagnostics.error && (
            <p className="text-sm text-destructive">
              {diagnostics.error.message}
            </p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>2. Browser microphone</CardTitle>
          <CardDescription>
            Dùng tai nghe. Dashboard chỉ lấy mic input; âm thanh loa vẫn có thể
            lọt vào mic vật lý.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <Status
            ok={browserReady}
            label="HTTPS/localhost + MediaDevices + AudioWorklet + WebSocket"
          />
          <Button
            type="button"
            onClick={testMic}
            disabled={mic.status === "checking"}
          >
            <Mic /> Kiểm tra microphone cục bộ
          </Button>
          <p role="status" className="text-sm">
            {mic.status === "pass" ? (
              <CheckCircle2 className="mr-2 inline size-4 text-green-600" />
            ) : (
              <CircleAlert className="mr-2 inline size-4 text-amber-600" />
            )}
            {mic.detail}{" "}
            {mic.peakRms !== undefined && `(peak RMS ${mic.peakRms})`}
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>3. Real session evidence</CardTitle>
          <CardDescription>
            Tạo Voice Real, mở overlay trong OBS, chạy ít nhất 60 giây rồi nhập
            session ID. Chi phí 3 giờ là ngoại suy từ usage thực và đơn giá do
            operator cấu hình, không phải hóa đơn provider.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <Button asChild variant="outline">
            <Link to="/live">Mở Live Setup</Link>
          </Button>
          <div className="flex gap-2">
            <Input
              aria-label="Real session ID"
              value={sessionId}
              onChange={(event) => setSessionId(event.target.value)}
              placeholder="UUID của phiên Voice Real"
            />
            <Button
              type="button"
              onClick={loadUsage}
              disabled={!sessionId.trim()}
            >
              Đọc metrics
            </Button>
          </div>
          {usageError && (
            <p className="text-sm text-destructive">{usageError}</p>
          )}
          {usage && (
            <div
              className="grid gap-2 rounded-lg border p-4 text-sm md:grid-cols-2"
              data-testid="real-usage-evidence"
            >
              <span>
                Scope: <strong>{usage.usage_measurement_scope}</strong>
              </span>
              <span>Observed: {usage.observed_session_seconds}s</span>
              <span>STT: {usage.stt_seconds}s</span>
              <span>
                LLM: {usage.llm_input_tokens}/{usage.llm_output_tokens} tokens
              </span>
              <span>TTS: {usage.tts_characters} characters</span>
              <span>
                3h estimate:{" "}
                {usage.projected_3h_usd == null
                  ? "chưa đủ dữ liệu/đơn giá"
                  : `$${usage.projected_3h_usd.toFixed(4)}`}
              </span>
              <span>Cost basis: {usage.usage_basis.estimated_usd}</span>
              <span>
                P50 E2E:{" "}
                {usage.telemetry.metrics.voice_end_to_first_playback_ack_ms
                  ?.p50_ms ?? "chưa đo"}{" "}
                ms
              </span>
              <span>
                P95 E2E:{" "}
                {usage.telemetry.metrics.voice_end_to_first_playback_ack_ms
                  ?.p95_ms ?? "chưa đo"}{" "}
                ms
              </span>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>4. Manual Vietnamese + OBS checklist</CardTitle>
          <CardDescription>
            Các dấu chọn dưới đây là xác nhận của operator, không tự biến thành
            PASS của CI.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {manualChecks.map((label, index) => (
            <label
              key={label}
              className="flex items-start gap-3 rounded-lg border p-3"
            >
              <input
                type="checkbox"
                checked={checked[index]}
                onChange={(event) =>
                  setChecked((current) =>
                    current.map((value, itemIndex) =>
                      itemIndex === index ? event.target.checked : value,
                    ),
                  )
                }
                className="mt-1"
              />
              <span>{label}</span>
            </label>
          ))}
          <Button type="button" variant="outline" onClick={exportEvidence}>
            <Download /> Xuất evidence JSON
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}
