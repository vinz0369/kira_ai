import type { LiveEvent } from "@/lib/liveApi"

type PlayerCallbacks = {
  sendAck: (
    type: string,
    utteranceId: string,
    metrics?: Record<string, number>,
  ) => void
  setSpeaking: (speaking: boolean, amplitude: number) => void
  setNeedsGesture: (needed: boolean) => void
}

export class PcmPlayer {
  private context: AudioContext | null = null
  private source: AudioBufferSourceNode | null = null
  private streamingSources = new Set<AudioBufferSourceNode>()
  private currentId: string | null = null
  private chunks = new Map<number, Int16Array>()
  private sampleRate = 24_000
  private cancelled = false
  private playStarted = false
  private firstChunkReceivedAt: number | null = null
  private finalizedIds: string[] = []
  private nextStartTime = 0
  private streamEnded = false
  private completionTimer: ReturnType<typeof setTimeout> | null = null

  constructor(private readonly callbacks: PlayerCallbacks) {}

  async unlock(): Promise<void> {
    const context = this.getContext()
    await context.resume()
    this.callbacks.setNeedsGesture(context.state !== "running")
    if (context.state === "running" && this.currentId && !this.playStarted)
      await this.play()
  }

  async handle(event: LiveEvent): Promise<void> {
    if (event.type === "speech.start") {
      const nextId = String(event.payload.utterance_id)
      if (this.currentId === nextId || this.finalizedIds.includes(nextId))
        return
      this.stop(false)
      this.currentId = nextId
      this.sampleRate = Number(event.payload.sample_rate_hz ?? 24_000)
      this.chunks.clear()
      this.cancelled = false
      this.playStarted = false
      this.firstChunkReceivedAt = null
      this.nextStartTime = 0
      this.streamEnded = false
      return
    }
    if (
      event.type === "speech.audio" &&
      String(event.payload.utterance_id) === this.currentId
    ) {
      this.firstChunkReceivedAt ??= performance.now()
      const binary = atob(String(event.payload.pcm_base64))
      const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0))
      this.chunks.set(
        Number(event.payload.chunk_index),
        new Int16Array(bytes.buffer),
      )
      return
    }
    if (
      event.type === "speech.end" &&
      String(event.payload.utterance_id) === this.currentId
    ) {
      this.streamEnded = true
      if (
        this.playStarted &&
        this.streamingSources.size === 0 &&
        !this.source
      ) {
        this.complete(String(event.payload.utterance_id))
        return
      }
      await this.play()
      if (
        this.currentId === String(event.payload.utterance_id) &&
        this.streamingSources.size > 0
      ) {
        const context = this.getContext()
        this.scheduleCompletion(
          this.currentId,
          Math.max(0, this.nextStartTime - context.currentTime),
        )
      }
      return
    }
    if (
      event.type === "speech.cancel" &&
      String(event.payload.utterance_id) === this.currentId
    ) {
      this.stop(true, performance.now())
    }
    if (
      event.type === "session.state" &&
      (event.payload.ai_muted || event.payload.status === "stopped")
    ) {
      this.stop(true, performance.now())
    }
  }

  async handleBinary(data: ArrayBuffer): Promise<void> {
    if (data.byteLength < 24 || !this.currentId || this.cancelled) return
    const view = new DataView(data)
    if (view.getUint8(0) !== 1 || view.getUint8(1) !== 2) return
    const idBytes = new Uint8Array(data, 6, 16)
    const hex = [...idBytes]
      .map((byte) => byte.toString(16).padStart(2, "0"))
      .join("")
    const streamId = `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
    if (streamId !== this.currentId) return
    this.firstChunkReceivedAt ??= performance.now()
    const pcm = new Int16Array(data.slice(22))
    await this.playStreamingChunk(pcm)
  }

  dispose(): void {
    this.stop(false)
    void this.context?.close()
    this.context = null
  }

  private getContext(): AudioContext {
    this.context ??= new AudioContext({
      latencyHint: "interactive",
      sampleRate: this.sampleRate,
    })
    return this.context
  }

  private async play(): Promise<void> {
    const id = this.currentId
    if (!id || this.cancelled || this.playStarted) return
    this.playStarted = true
    const samples = [...this.chunks.entries()]
      .sort(([a], [b]) => a - b)
      .map(([, value]) => value)
    const total = samples.reduce((sum, chunk) => sum + chunk.length, 0)
    if (!total) {
      this.playStarted = false
      return
    }
    const context = this.getContext()
    try {
      await context.resume()
    } catch {
      this.playStarted = false
      this.callbacks.setNeedsGesture(true)
      return
    }
    if (context.state !== "running") {
      this.playStarted = false
      this.callbacks.setNeedsGesture(true)
      return
    }
    const audio = context.createBuffer(1, total, this.sampleRate)
    const channel = audio.getChannelData(0)
    let offset = 0
    let peak = 0
    for (const chunk of samples) {
      for (const value of chunk) {
        const normalized = value / 32768
        channel[offset++] = normalized
        peak = Math.max(peak, Math.abs(normalized))
      }
    }
    const source = context.createBufferSource()
    source.buffer = audio
    source.connect(context.destination)
    this.source = source
    this.callbacks.setSpeaking(true, Math.max(0.25, peak))
    this.callbacks.sendAck("speech.playback.started", id, {
      client_first_chunk_to_playback_ms: Math.max(
        0,
        performance.now() - (this.firstChunkReceivedAt ?? performance.now()),
      ),
    })
    source.onended = () => {
      if (this.cancelled || this.currentId !== id) return
      this.source = null
      this.complete(id)
    }
    source.start()
    this.scheduleCompletion(id, audio.duration)
  }

  private stop(sendAck: boolean, cancellationStartedAt?: number): void {
    const id = this.currentId
    this.cancelled = true
    if (this.source) {
      this.source.onended = null
      try {
        this.source.stop()
      } catch {
        // Already stopped; cancellation is idempotent.
      }
    }
    this.source = null
    for (const source of this.streamingSources) {
      source.onended = null
      try {
        source.stop()
      } catch {
        // Already stopped.
      }
    }
    this.streamingSources.clear()
    this.currentId = null
    this.chunks.clear()
    this.playStarted = false
    this.firstChunkReceivedAt = null
    this.nextStartTime = 0
    this.streamEnded = false
    if (this.completionTimer) clearTimeout(this.completionTimer)
    this.completionTimer = null
    this.callbacks.setSpeaking(false, 0)
    if (sendAck && id) {
      this.finalize(id)
      this.callbacks.sendAck("speech.playback.cancelled", id, {
        client_audio_stop_ms: Math.max(
          0,
          performance.now() - (cancellationStartedAt ?? performance.now()),
        ),
      })
    }
  }

  private async playStreamingChunk(samples: Int16Array): Promise<void> {
    const id = this.currentId
    if (!id || !samples.length) return
    const context = this.getContext()
    try {
      await context.resume()
    } catch {
      this.callbacks.setNeedsGesture(true)
      return
    }
    if (context.state !== "running") {
      this.callbacks.setNeedsGesture(true)
      return
    }
    const audio = context.createBuffer(1, samples.length, this.sampleRate)
    const channel = audio.getChannelData(0)
    let peak = 0
    for (let index = 0; index < samples.length; index++) {
      const normalized = (samples[index] ?? 0) / 32768
      channel[index] = normalized
      peak = Math.max(peak, Math.abs(normalized))
    }
    const source = context.createBufferSource()
    source.buffer = audio
    source.connect(context.destination)
    const startsAt = Math.max(context.currentTime + 0.025, this.nextStartTime)
    this.nextStartTime = startsAt + audio.duration
    this.streamingSources.add(source)
    if (!this.playStarted) {
      this.playStarted = true
      this.callbacks.setSpeaking(true, Math.max(0.25, peak))
      this.callbacks.sendAck("speech.playback.started", id, {
        client_first_chunk_to_playback_ms: Math.max(
          0,
          performance.now() - (this.firstChunkReceivedAt ?? performance.now()),
        ),
      })
    }
    source.onended = () => {
      this.streamingSources.delete(source)
      if (
        this.streamEnded &&
        this.streamingSources.size === 0 &&
        this.currentId === id
      )
        this.complete(id)
    }
    source.start(startsAt)
  }

  private complete(id: string): void {
    if (this.currentId !== id || this.cancelled) return
    if (this.completionTimer) clearTimeout(this.completionTimer)
    this.completionTimer = null
    this.currentId = null
    this.chunks.clear()
    this.finalize(id)
    this.callbacks.setSpeaking(false, 0)
    this.callbacks.sendAck("speech.playback.completed", id)
  }

  private scheduleCompletion(id: string, remainingSeconds: number): void {
    if (this.completionTimer) clearTimeout(this.completionTimer)
    this.completionTimer = setTimeout(
      () => {
        if (this.currentId !== id || this.cancelled) return
        if (this.source) {
          this.source.onended = null
          try {
            this.source.stop()
          } catch {
            // The normal onended path may have won this race.
          }
          this.source = null
        }
        for (const source of this.streamingSources) {
          source.onended = null
          try {
            source.stop()
          } catch {
            // The normal onended path may have won this race.
          }
        }
        this.streamingSources.clear()
        this.complete(id)
      },
      Math.max(0, remainingSeconds) * 1000 + 500,
    )
  }

  private finalize(id: string): void {
    this.finalizedIds.push(id)
    if (this.finalizedIds.length > 200) this.finalizedIds.shift()
  }
}
