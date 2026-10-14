export type Character = {
  id: string
  owner_id: string
  name: string
  template_id: string
  persona_description: string
  address_streamer_as: string
  viewer_style: string
  humor_level: string
  proactivity: string
  llm_provider: string
  llm_model: string
  voice_provider: string
  voice_id: string
  avatar_asset_id: string | null
  avatar_camera_framing: "chest-up" | "full-body"
  avatar_camera_zoom: number
  memory_opt_in: boolean
  created_at: string
  updated_at: string
}

export type TtsProviderOption = {
  id: string
  label: string
  description: string
  experimental: boolean
  credential_required: boolean
  available: boolean
  voices: Array<{ id: string; label: string }>
}

export type LlmProviderOption = {
  id: string
  label: string
  description: string
  credential_required: boolean
  available: boolean
  models: Array<{ id: string; label: string }>
}

export type LiveSession = {
  id: string
  character_id: string
  mode: string
  voice_mode: "mock" | "real"
  status: "draft" | "active" | "paused" | "stopped"
  ai_muted: boolean
  mic_connected: boolean
  session_epoch: number
  created_at: string
  updated_at: string
  overlay_url: string | null
  youtube_broadcast_id: string | null
  youtube_live_chat_id: string | null
  youtube_ingest_status: string
  youtube_last_error: string | null
  real_voice_configured: boolean
}

export type YouTubeConnection = {
  configured: boolean
  connected: boolean
  status: string
  channel_id: string | null
  channel_name: string | null
  granted_scopes: string[]
  expires_at: string | null
  needs_reconnect: boolean
  last_error_code: string | null
}

export type YouTubeBroadcast = {
  id: string
  title: string
  live_chat_id: string
  actual_start_time: string | null
  life_cycle_status: string
}

export type Phase3Diagnostics = {
  measurement_scope: "PREFLIGHT_ONLY"
  real_voice_ready: boolean
  deepgram: { configured: boolean; status: string; model: string }
  fpt_llm: { configured: boolean; status: string; model: string }
  openai: { configured: boolean; status: string; model: string }
  google_tts: { configured: boolean; status: string; model: string }
  gtts: { configured: boolean; status: string; model: string }
  edge_tts: { configured: boolean; status: string; model: string }
  cost_rates_configured: boolean
  youtube_oauth_configured: boolean
  youtube_connected: boolean
  raw_audio_persisted: boolean
  secrets_exposed_to_frontend: boolean
}

export type SessionUsage = {
  stt_seconds: number
  llm_input_tokens: number
  llm_output_tokens: number
  tts_characters: number
  estimated_usd: number | null
  cost_estimate_configured: boolean
  observed_session_seconds: number
  projected_3h_usd: number | null
  projection_basis: "actual_usage_run_rate" | "unavailable"
  usage_measurement_scope: "MOCK_SIMULATED" | "REAL_PROVIDER_OBSERVED"
  usage_basis: Record<string, string>
  provider_errors: number
  stt_reconnects: number
  dropped_mic_frames: number
  overlay_reconnect_count: number
  telemetry: {
    measurement_scope: "MOCK_SIMULATED_LOCAL" | "REAL_PROVIDER_LOCAL"
    metrics: Record<
      string,
      {
        samples: number
        latest_ms: number
        p50_ms: number
        p95_ms: number
      }
    >
    recent_traces: Array<{
      trace_id: string
      utterance_id: string
      input_event_type: string
      measurement_scope: string
      metrics_ms: Record<string, number>
    }>
  }
}

export type LiveEvent = {
  v: 1
  event_id: string
  session_id: string
  type: string
  ts: string
  source: string
  payload: Record<string, unknown>
}

const apiBase = import.meta.env.VITE_API_URL ?? ""

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = localStorage.getItem("access_token")
  const response = await fetch(`${apiBase}/api/v1${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init?.headers,
    },
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    const detail =
      typeof body?.detail === "string"
        ? body.detail
        : typeof body?.message === "string"
          ? body.message
          : null
    throw new Error(
      detail && !["Not Found", "Method Not Allowed"].includes(detail)
        ? detail
        : `HTTP ${response.status}`,
    )
  }
  return response.json() as Promise<T>
}

export const liveApi = {
  listCharacters: () =>
    request<{ data: Character[]; count: number }>("/characters/"),
  getCharacter: (id: string) => request<Character>(`/characters/${id}`),
  ttsVoiceOptions: () =>
    request<TtsProviderOption[]>("/characters/voice-options"),
  llmOptions: () => request<LlmProviderOption[]>("/characters/llm-options"),
  createCharacter: (body: Partial<Character>) =>
    request<Character>("/characters/", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  updateCharacter: (id: string, body: Partial<Character>) =>
    request<Character>(`/characters/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  createSession: (
    characterId: string,
    mode: "mock" | "youtube" = "mock",
    youtubeBroadcastId?: string,
    voiceMode: "mock" | "real" = "mock",
  ) =>
    request<LiveSession>("/sessions/", {
      method: "POST",
      body: JSON.stringify({
        character_id: characterId,
        mode,
        voice_mode: voiceMode,
        youtube_broadcast_id: youtubeBroadcastId,
      }),
    }),
  getSession: (id: string) => request<LiveSession>(`/sessions/${id}`),
  currentSession: () => request<LiveSession | null>("/sessions/current"),
  listSessions: () => request<LiveSession[]>("/sessions/"),
  control: (id: string, command: string) =>
    request<LiveSession>(`/sessions/${id}/control`, {
      method: "POST",
      body: JSON.stringify({ command }),
    }),
  avatarMotion: (
    id: string,
    motion: "idle" | "greet" | "heart" | "dance",
    durationSeconds = 0,
  ) =>
    request<{ motion: string; duration_seconds: number }>(
      `/sessions/${id}/avatar-motion`,
      {
        method: "POST",
        body: JSON.stringify({ motion, duration_seconds: durationSeconds }),
      },
    ),
  rotateOverlayKey: (id: string) =>
    request<LiveSession>(`/sessions/${id}/overlay-key/rotate`, {
      method: "POST",
    }),
  ticket: (id: string) =>
    request<{ ticket: string; expires_in_seconds: number }>(
      `/sessions/${id}/ws-ticket`,
      {
        method: "POST",
      },
    ),
  simulate: (id: string, type: string, payload: Record<string, unknown>) =>
    request<{ accepted: boolean; events: LiveEvent[]; queue_depth: number }>(
      `/sessions/${id}/simulate`,
      { method: "POST", body: JSON.stringify({ type, payload }) },
    ),
  usage: (id: string) => request<SessionUsage>(`/sessions/${id}/usage`),
  phase3Diagnostics: () => request<Phase3Diagnostics>("/diagnostics/phase3"),
  youtubeConnection: () => request<YouTubeConnection>("/youtube/connection"),
  youtubeAuthorize: () =>
    request<{ authorization_url: string }>("/youtube/oauth/authorize", {
      method: "POST",
    }),
  youtubeDisconnect: () =>
    request<{ disconnected: boolean; revocation_status: string }>(
      "/youtube/connection",
      { method: "DELETE" },
    ),
  youtubeBroadcasts: () => request<YouTubeBroadcast[]>("/youtube/broadcasts"),
  resolveYoutubeBroadcast: (videoUrl: string) =>
    request<YouTubeBroadcast>("/youtube/broadcasts/resolve", {
      method: "POST",
      body: JSON.stringify({ video_url: videoUrl }),
    }),
  reconnectYoutube: (id: string) =>
    request<LiveSession>(`/sessions/${id}/youtube/reconnect`, {
      method: "POST",
    }),
  bindYoutubeBroadcast: (id: string, videoUrl: string) =>
    request<LiveSession>(`/sessions/${id}/youtube/bind`, {
      method: "POST",
      body: JSON.stringify({ video_url: videoUrl }),
    }),
}

export function websocketBase(): string {
  const configured = import.meta.env.VITE_WS_URL
  if (configured) return configured.replace(/\/$/, "")
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:"
  return `${protocol}//${window.location.host}`
}
