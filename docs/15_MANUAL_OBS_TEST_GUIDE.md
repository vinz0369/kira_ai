# Manual OBS Browser Source verification

Status: **PARTIAL OPERATOR-REPORTED**. On 2026-10-14 OBS Studio 32.0.4 was open, the operator saw Kira's Browser Source and gave an affirmative audio/animation report. Transparency, exactly-once playback, mixer routing, local recording, audio feedback, manual no-replay after Stop, and audible latency were not individually verified; complete this guide before claiming OBS PASS.

The Chromium Playwright test verifies the transparent page background, WebGL canvas, overlay-only audio ownership, talking/idle state transitions, cancellation, and reconnect behavior. OBS uses an embedded browser, so the following desktop smoke test is still required before claiming OBS compatibility.

For Arcana, first confirm the operator-supplied character (not the geometric fallback) is visible. Arcana is deliberately **local-development only** because its embedded terms prohibit redistribution and commercial use. Keep OBS on the same machine as the backend and frontend; the private model and VMD requests require the session's overlay key and a loopback client. Never copy `Arcana.vrm` or the 2 Phut Hon assets into `frontend/public`, and do not stream them commercially without suitable grants. In Character Studio select **Từ ngực lên** or **Toàn thân**, adjust **Thu phóng**, save, and verify OBS uses the saved framing. Try **Vẫy tay chào**, **Tạo hình trái tim**, and **Dance 2 Phút Hơn (local)**; confirm the real motion runs, loops five times for up to 150 seconds, then returns to idle or stops immediately. Inspect the avatar canvas in browser diagnostics: `data-dance-source="2-phut-hon-vmd"` means the VMD loaded; `cc0-fallback` means it did not. The supplied song WAV is intentionally silent/unserved—only the animation is integrated. Pause/Stop/reconnect must return to idle and reconnect must not restart dance. The `.warudo` file belongs to Warudo and is not used by this Browser Source.

## Prerequisites

1. Start PostgreSQL, the backend, and frontend as documented in `README.md`. Mailpit is required for the full Playwright suite; Redis is only needed if the selected deployment uses it.
2. Open `/settings/diagnostics` and export the local diagnostic evidence after completing the browser and provider checks that apply to this run.
3. Sign in, create a character, create either a mock session or a real voice session, and click **Start**.
4. Copy the password-masked overlay URL. Do not show or log its `key` query parameter.
5. Note the OBS Studio version, Windows version, CPU, GPU, and audio devices for the test report.

## Browser Source setup

1. In OBS, add **Source -> Browser** and name it `AI Character`.
2. Paste the overlay URL.
3. Set width `1280`, height `720` (matching the control-room hint), or `1920` x `1080` if that matches the OBS scene; use FPS `30` or `60` according to the stream profile.
4. Enable **Control audio via OBS**.
5. Leave custom CSS empty. The overlay already uses a transparent HTML/body/canvas background.
6. Do not enable page refresh when the scene merely becomes inactive; an unnecessary refresh intentionally drops current speech rather than replaying it.

## Required checks

Record each item as PASS or FAIL with the observed value.

1. **Transparency:** the avatar renders over a color or game source with no opaque rectangle.
2. **Single audio path:** inject one mock voice event and confirm exactly one meter moves for the Browser Source. The Dashboard must remain silent.
3. **Talking/idle:** the mouth moves while the tone is audible and returns to idle after playback.
4. **Mute:** inject another event, click Mute during playback, and time until the OBS meter becomes silent. Target is below 200 ms locally.
5. **Stop:** inject another event, click Stop, and confirm audio stops, the overlay reports expiration, and the old URL cannot reconnect.
6. **Reconnect:** during an idle period, use **Refresh cache of current page**. Confirm the avatar reconnects idle and no previous tone replays.
7. **Routing/echo:** make a 30–60 second local recording. Confirm the AI tone is present once. If the streamer needs to hear it, choose **Monitor and Output** in Advanced Audio Properties and ensure the monitoring device is not also recaptured by Desktop Audio.
8. **Performance:** record OBS Browser Source CPU, total OBS CPU, rendered/missed frames, GPU utilization, and memory for at least five minutes with repeated mock events.

## Troubleshooting

- No audio: open Browser Source properties, enable OBS-controlled audio, then check that its mixer channel is not muted.
- Double audio/echo: use one Browser Source only; disable Dashboard preview audio; prevent the monitoring device from being captured again by Desktop Audio.
- Opaque background: remove custom Browser Source CSS and verify browser hardware acceleration is enabled.
- Autoplay prompt: interact with the browser preview once. OBS Browser Source normally permits autoplay, but browser preview tabs may require the **Bật audio preview** button.
- Old URL rejected after Stop: expected. Create a new session or rotate the overlay key before starting again.

## Report template

```text
Date/time:
Diagnostic evidence JSON filename:
OBS Studio version:
Windows / CPU / GPU:
Overlay resolution/FPS:
Transparency: PASS/FAIL
Single playback: PASS/FAIL
Talking -> idle: PASS/FAIL
Mute latency samples (ms):
Stop/revocation: PASS/FAIL
Reconnect without replay: PASS/FAIL
Recording contains one audio path: PASS/FAIL
OBS CPU/GPU/RAM/frame observations:
Notes/blockers:
```
