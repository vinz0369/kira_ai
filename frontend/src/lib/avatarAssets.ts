import { useEffect, useState } from "react"

export const ARCANA_LOCAL_ID = "arcana-local"
const LEGACY_AVATAR_ID = "avatar-sample-b"
type LocalAssetAccess = { sessionId: string; key: string } | null
type PrivateAssetState = "loading" | "available" | "unavailable"

export function effectiveAvatarId(
  assetId: string | null | undefined,
  characterName?: string,
): string | null {
  if (assetId === LEGACY_AVATAR_ID && characterName?.toLowerCase() === "kira")
    return ARCANA_LOCAL_ID
  return (
    assetId ??
    (characterName?.toLowerCase() === "kira" ? ARCANA_LOCAL_ID : null)
  )
}

/** A blob URL keeps the operator's private VRM out of Vite's public build. */
export function useLocalAvatarUrl(
  assetId: string | null | undefined,
  access: LocalAssetAccess = null,
  characterName?: string,
): string | undefined {
  const [url, setUrl] = useState<string>()
  const effectiveId = effectiveAvatarId(assetId, characterName)
  const sessionId = access?.sessionId
  const key = access?.key
  useEffect(() => {
    setUrl(undefined)
    if (effectiveId !== ARCANA_LOCAL_ID) return
    const controller = new AbortController()
    let objectUrl: string | undefined
    const token = sessionId ? null : localStorage.getItem("access_token")
    if (!sessionId && !token) return
    const base = import.meta.env.VITE_API_URL ?? ""
    const path = sessionId
      ? `/api/v1/avatar-assets/arcana/overlay/${sessionId}`
      : "/api/v1/avatar-assets/arcana/studio"
    void fetch(`${base}${path}`, {
      signal: controller.signal,
      headers: sessionId
        ? { "X-Overlay-Key": key ?? "" }
        : { Authorization: `Bearer ${token}` },
    })
      .then((response) => {
        if (!response.ok) throw new Error("Private VRM unavailable")
        return response.blob()
      })
      .then((blob) => {
        if (controller.signal.aborted) return
        objectUrl = URL.createObjectURL(blob)
        setUrl(objectUrl)
      })
      .catch(() => {
        if (!controller.signal.aborted) setUrl(undefined)
      })
    return () => {
      controller.abort()
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [effectiveId, key, sessionId])
  return url
}

/**
 * The operator-provided VMD is intentionally fetched only from the local,
 * authenticated development route. It is motion-only: the supplied WAV is
 * never requested or played by the overlay.
 */
export function useLocal2PhutHonMotion(
  access: LocalAssetAccess = null,
  enabled = true,
): {
  url?: string
  state: PrivateAssetState
} {
  const [url, setUrl] = useState<string>()
  const [state, setState] = useState<PrivateAssetState>("loading")
  const sessionId = access?.sessionId
  const key = access?.key
  useEffect(() => {
    if (!enabled) {
      setUrl(undefined)
      setState("loading")
      return
    }
    const controller = new AbortController()
    let objectUrl: string | undefined
    const token = sessionId ? null : localStorage.getItem("access_token")
    if (!sessionId && !token) {
      setUrl(undefined)
      setState("unavailable")
      return
    }
    setUrl(undefined)
    setState("loading")
    const base = import.meta.env.VITE_API_URL ?? ""
    const path = sessionId
      ? `/api/v1/avatar-assets/motions/2-phut-hon/overlay/${sessionId}`
      : "/api/v1/avatar-assets/motions/2-phut-hon/studio"
    void fetch(`${base}${path}`, {
      signal: controller.signal,
      headers: sessionId
        ? { "X-Overlay-Key": key ?? "" }
        : { Authorization: `Bearer ${token}` },
    })
      .then((response) => {
        if (!response.ok) throw new Error("Private dance motion unavailable")
        return response.blob()
      })
      .then((blob) => {
        if (controller.signal.aborted) return
        objectUrl = URL.createObjectURL(blob)
        setUrl(objectUrl)
        setState("available")
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setUrl(undefined)
          setState("unavailable")
        }
      })
    return () => {
      controller.abort()
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [enabled, key, sessionId])
  return { url, state }
}
