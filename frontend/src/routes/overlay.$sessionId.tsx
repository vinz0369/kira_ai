import { createFileRoute } from "@tanstack/react-router"
import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react"

import { PcmPlayer } from "@/components/Live/PcmPlayer"
import { useLocal2PhutHonMotion, useLocalAvatarUrl } from "@/lib/avatarAssets"
import type { LiveEvent } from "@/lib/liveApi"
import { websocketBase } from "@/lib/liveApi"

type OverlaySearch = { key: string }

const AvatarScene = lazy(() =>
  import("@/components/Live/AvatarScene").then((module) => ({
    default: module.AvatarScene,
  })),
)

export const Route = createFileRoute("/overlay/$sessionId")({
  validateSearch: (search: Record<string, unknown>): OverlaySearch => ({
    key: typeof search.key === "string" ? search.key : "",
  }),
  component: Overlay,
})

function Overlay() {
  const { sessionId } = Route.useParams()
  const { key } = Route.useSearch()
  const socketRef = useRef<WebSocket | null>(null)
  const [speaking, setSpeaking] = useState(false)
  const [amplitude, setAmplitude] = useState(0)
  const [mood, setMood] = useState<
    "neutral" | "happy" | "annoyed" | "surprised" | "sad" | "relaxed" | "wink"
  >("neutral")
  const [needsGesture, setNeedsGesture] = useState(false)
  const [connection, setConnection] = useState("connecting")
  const [avatarAssetId, setAvatarAssetId] = useState<string | null>(null)
  const [motion, setMotion] = useState<"idle" | "greet" | "heart" | "dance">(
    "idle",
  )
  const [cameraFraming, setCameraFraming] = useState<"chest-up" | "full-body">(
    "chest-up",
  )
  const [cameraZoom, setCameraZoom] = useState(1)
  const motionTimer = useRef<ReturnType<typeof setTimeout> | undefined>(
    undefined,
  )
  const vrmUrl = useLocalAvatarUrl(avatarAssetId, { sessionId, key })
  const danceMotion = useLocal2PhutHonMotion(
    { sessionId, key },
    motion === "dance" && connection === "connected",
  )
  const player = useMemo(
    () =>
      new PcmPlayer({
        sendAck: (type, utteranceId, metrics = {}) => {
          const socket = socketRef.current
          if (socket?.readyState !== WebSocket.OPEN) return
          socket.send(
            JSON.stringify({
              v: 1,
              event_id: crypto.randomUUID(),
              session_id: sessionId,
              type,
              ts: new Date().toISOString(),
              source: "overlay",
              payload: { utterance_id: utteranceId, ...metrics },
            }),
          )
        },
        setSpeaking: (active, level) => {
          setSpeaking(active)
          setAmplitude(level)
        },
        setNeedsGesture,
      }),
    [sessionId],
  )
  useEffect(() => {
    const previous = document.body.style.background
    document.body.style.background = "transparent"
    document.documentElement.style.background = "transparent"
    return () => {
      document.body.style.background = previous
      document.documentElement.style.background = ""
    }
  }, [])
  useEffect(() => {
    if (!key) {
      setConnection("invalid-key")
      return
    }
    let stopped = false
    let attempts = 0
    let retry: ReturnType<typeof setTimeout> | undefined
    const connect = () => {
      const socket = new WebSocket(
        `${websocketBase()}/ws/v1/overlay/${sessionId}?key=${encodeURIComponent(key)}`,
      )
      socket.binaryType = "arraybuffer"
      socketRef.current = socket
      socket.onopen = () => {
        attempts = 0
        setConnection("connected")
      }
      socket.onmessage = (message) => {
        if (message.data instanceof ArrayBuffer) {
          void player.handleBinary(message.data)
          return
        }
        const event = JSON.parse(message.data) as LiveEvent
        if (event.type === "character.state") {
          setMood((event.payload.mood as typeof mood) ?? "neutral")
          if (!event.payload.speaking) setSpeaking(false)
        }
        if (event.type === "session.state") {
          setAvatarAssetId(
            typeof event.payload.avatar_asset_id === "string"
              ? event.payload.avatar_asset_id
              : null,
          )
          if (
            event.payload.avatar_camera_framing === "chest-up" ||
            event.payload.avatar_camera_framing === "full-body"
          )
            setCameraFraming(event.payload.avatar_camera_framing)
          if (typeof event.payload.avatar_camera_zoom === "number")
            setCameraZoom(event.payload.avatar_camera_zoom)
        }
        if (event.type === "avatar.motion") {
          if (motionTimer.current) clearTimeout(motionTimer.current)
          const next = event.payload.motion
          setMotion(
            next === "greet" || next === "heart" || next === "dance"
              ? next
              : "idle",
          )
          const duration = Number(event.payload.duration_seconds ?? 0)
          if (duration > 0)
            motionTimer.current = setTimeout(
              () => setMotion("idle"),
              duration * 1000,
            )
        }
        if (event.type === "session.control") {
          if (["stop", "pause"].includes(String(event.payload.command))) {
            if (motionTimer.current) clearTimeout(motionTimer.current)
            setMotion("idle")
          }
        }
        void player.handle(event)
      }
      socket.onclose = (event) => {
        if (motionTimer.current) clearTimeout(motionTimer.current)
        setMotion("idle")
        setConnection(
          event.code === 4003 || event.code === 1008
            ? "revoked"
            : "reconnecting",
        )
        if (!stopped && event.code !== 4003 && event.code !== 1008)
          retry = setTimeout(connect, Math.min(5000, 500 * 2 ** attempts++))
      }
    }
    connect()
    return () => {
      stopped = true
      if (retry) clearTimeout(retry)
      if (motionTimer.current) clearTimeout(motionTimer.current)
      socketRef.current?.close()
      player.dispose()
    }
  }, [key, player, sessionId])
  return (
    <main
      className="fixed inset-0 overflow-hidden bg-transparent"
      data-testid="obs-overlay"
      data-connection={connection}
      data-speaking={speaking ? "true" : "false"}
      data-mood={mood}
      data-audio-owner="overlay"
    >
      <Suspense fallback={null}>
        <AvatarScene
          speaking={speaking}
          amplitude={amplitude}
          mood={mood}
          motion={
            motion !== "idle" && connection === "connected" ? motion : "idle"
          }
          cameraFraming={cameraFraming}
          cameraZoom={cameraZoom}
          danceVmdUrl={danceMotion.url}
          danceVmdState={danceMotion.state}
          vrmUrl={vrmUrl}
        />
      </Suspense>
      {motion === "heart" && connection === "connected" && (
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-x-0 top-[18%] text-center text-5xl drop-shadow-lg"
        >
          💕 <span className="inline-block -translate-y-8 text-3xl">💗</span> 💕
        </div>
      )}
      {needsGesture && (
        <button
          type="button"
          onClick={() => player.unlock()}
          className="absolute bottom-6 left-1/2 -translate-x-1/2 rounded-full bg-black/70 px-5 py-3 text-white"
        >
          Bật audio preview
        </button>
      )}
      {connection !== "connected" && (
        <div className="absolute left-4 top-4 rounded bg-black/60 px-3 py-2 text-sm text-white">
          {connection === "revoked" ? "Overlay đã hết hạn" : "Đang kết nối…"}
        </div>
      )}
      <span className="sr-only" aria-live="polite">
        {speaking ? "Nhân vật đang nói" : "Nhân vật đang chờ"}
      </span>
    </main>
  )
}
