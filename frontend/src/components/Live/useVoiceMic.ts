import { useCallback, useEffect, useRef, useState } from "react"

import type { LiveEvent } from "@/lib/liveApi"

type SendSocket = (data: string | ArrayBuffer) => boolean

export type MicState = "off" | "loading" | "listening" | "speaking" | "error"

function event(sessionId: string, type: string, turnId: string): string {
  const body: LiveEvent = {
    v: 1,
    event_id: crypto.randomUUID(),
    session_id: sessionId,
    type,
    ts: new Date().toISOString(),
    source: "voice",
    payload: { turn_id: turnId },
  }
  return JSON.stringify(body)
}

function pcmFrame(turnId: string, sequence: number, samples: Float32Array) {
  const bytes = new Uint8Array(22 + samples.length * 2)
  const view = new DataView(bytes.buffer)
  view.setUint8(0, 1)
  view.setUint8(1, 1)
  view.setUint32(2, sequence, false)
  const uuid = turnId.replace(/-/g, "")
  for (let index = 0; index < 16; index++)
    bytes[6 + index] = Number.parseInt(uuid.slice(index * 2, index * 2 + 2), 16)
  for (let index = 0; index < samples.length; index++) {
    const sample = Math.max(-1, Math.min(1, samples[index] ?? 0))
    view.setInt16(
      22 + index * 2,
      sample < 0 ? sample * 0x8000 : sample * 0x7fff,
      true,
    )
  }
  return bytes.buffer
}

export function useVoiceMic(
  sessionId: string,
  enabled: boolean,
  send: SendSocket,
) {
  const [state, setState] = useState<MicState>("off")
  const [level, setLevel] = useState(0)
  const [error, setError] = useState("")
  const vadRef = useRef<Awaited<
    ReturnType<typeof import("@ricky0123/vad-web")["MicVAD"]["new"]>
  > | null>(null)
  const activeTurn = useRef<string | null>(null)
  const enabledRef = useRef(enabled)
  enabledRef.current = enabled
  const sequence = useRef(0)
  const preRoll = useRef<Float32Array[]>([])

  const stop = useCallback(async () => {
    const turnId = activeTurn.current
    if (turnId) send(event(sessionId, "streamer.speech.ended", turnId))
    activeTurn.current = null
    if (vadRef.current) await vadRef.current.destroy()
    vadRef.current = null
    preRoll.current = []
    setLevel(0)
    setState("off")
  }, [send, sessionId])

  const start = useCallback(async () => {
    if (!enabled || vadRef.current) return
    setState("loading")
    setError("")
    try {
      const { MicVAD } = await import("@ricky0123/vad-web")
      const vad = await MicVAD.new({
        model: "v5",
        processorType: "AudioWorklet",
        baseAssetPath: "/vad/",
        onnxWASMBasePath: "/vad/",
        startOnLoad: false,
        positiveSpeechThreshold: 0.65,
        negativeSpeechThreshold: 0.42,
        redemptionMs: 192,
        preSpeechPadMs: 192,
        minSpeechMs: 96,
        getStream: () =>
          navigator.mediaDevices.getUserMedia({
            audio: {
              channelCount: 1,
              echoCancellation: true,
              noiseSuppression: true,
              autoGainControl: true,
            },
          }),
        onSpeechStart: () => {
          const turnId = crypto.randomUUID()
          activeTurn.current = turnId
          sequence.current = 0
          send(event(sessionId, "streamer.speech.started", turnId))
          for (const frame of preRoll.current)
            send(pcmFrame(turnId, sequence.current++, frame))
          preRoll.current = []
          setState("speaking")
        },
        onSpeechRealStart: () => setState("speaking"),
        onFrameProcessed: (probabilities, frame) => {
          setLevel(probabilities.isSpeech)
          const turnId = activeTurn.current
          if (turnId) {
            send(pcmFrame(turnId, sequence.current++, frame))
          } else {
            preRoll.current.push(frame.slice())
            if (preRoll.current.length > 6) preRoll.current.shift()
          }
        },
        onSpeechEnd: () => {
          const turnId = activeTurn.current
          if (turnId) send(event(sessionId, "streamer.speech.ended", turnId))
          activeTurn.current = null
          setState("listening")
        },
        onVADMisfire: () => {
          const turnId = activeTurn.current
          if (turnId) send(event(sessionId, "streamer.speech.ended", turnId))
          activeTurn.current = null
          setState("listening")
        },
      })
      if (!enabledRef.current) {
        await vad.destroy()
        setState("off")
        return
      }
      vadRef.current = vad
      await vad.start()
      if (!enabledRef.current) {
        await stop()
        return
      }
      setState("listening")
    } catch (cause) {
      const vad = vadRef.current
      vadRef.current = null
      if (vad) {
        try {
          await vad.destroy()
        } catch {
          // Preserve the startup error shown to the operator.
        }
      }
      if (!enabledRef.current) {
        setState("off")
        return
      }
      setError(
        cause instanceof Error ? cause.message : "Không mở được microphone",
      )
      setState("error")
    }
  }, [enabled, send, sessionId, stop])

  useEffect(() => {
    if (!enabled && vadRef.current) void stop()
  }, [enabled, stop])
  useEffect(() => () => void stop(), [stop])
  return { state, level, error, start, stop }
}
