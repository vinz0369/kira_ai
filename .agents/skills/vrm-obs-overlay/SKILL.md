---
name: vrm-obs-overlay
description: Implement low-overhead Three-VRM avatar with React Three Fiber and OBS Browser Source overlay, synchronized speech playback and safe model licensing.
---
# 3D OBS overlay

Read `docs/03_USER_EXPERIENCE.md`, `docs/02_SYSTEM_ARCHITECTURE.md`, `docs/11_GITHUB_REUSE_MATRIX.md`.

## Procedure

1. Use `@react-three/fiber`, `@react-three/drei`, `@pixiv/three-vrm` inside React/Vite, not a hand-written 3D engine.
2. For first runnable mock include a 3D procedural mascot with idle/talking and 3+ expressions. Later load licensed VRM (verify *commercial redistribution* right and record model/texture licenses).
3. Route `/overlay/:sessionId` with transparent background, a single audio player context and no Dashboard audio duplication in live mode.
4. Handle `speech.start`/ordered chunks/`speech.end`/`speech.cancel`, send playback ACK, animate mouth by amplitude in MVP. Do not promise Vietnamese phoneme-accurate visemes.
5. On reconnect restore avatar state but never replay finished/stale speech. On Mute/Stop immediately stop audible sound independent of LLM.
6. Profile FPS/CPU/GPU usage in Chromium and OBS Browser Source if available; avoid heavy physics and full-body animations.

## Done when

Overlay renders in browser and, when OBS is available, Browser Source with transparent background; audio only once, mute instant, reload safe; asset license register complete.
