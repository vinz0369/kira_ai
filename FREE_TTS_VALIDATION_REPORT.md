# Free Vietnamese TTS validation report

Date: 2026-10-13  
Scope: Phase 3 provider extension only. Phase 4 was not started.

## Outcome labels

- `REAL_CREDENTIAL_FREE_TTS_NETWORK_TESTED`: gTTS and experimental Edge made real outbound synthesis calls; MP3 was decoded to PCM16 mono 24 kHz in memory.
- `AUTOMATED_SIGNAL_TESTED`: duration, RMS, peak and clipping were measured from decoded PCM.
- `HUMAN_VOICE_QUALITY_NOT_TESTED`: no operator listening/MOS rating was performed. Naturalness, Vietnamese pronunciation and gaming slang remain unclaimed.
- `OBS_NOT_TESTED`: the benchmark did not launch OBS or measure audible playback.
- `FULL_REAL_PIPELINE_NOT_TESTED`: Deepgram/OpenAI credentials and a human microphone run were not available.

## Implementation

- Existing `StreamingTts.stream(text, context_id) -> AsyncIterator[bytes]` contract is unchanged.
- gTTS 2.5.4 is the default credential-free Vietnamese option (`vi`). It needs internet but no Google Cloud credential.
- Edge TTS 7.2.8 is disabled by default and labeled experimental. The app allowlists Hoài My and Nam Minh Vietnamese voices and retries one no-audio failure.
- PyAV 16.1.0 decodes provider MP3 to the existing PCM16/24 kHz/mono wire format without writing runtime audio to disk.
- Mock Mode, Google Chirp, local degraded fallback, cancellation generations, OBS-only playback, exactly-once handling and amplitude lip-sync are preserved.
- Character Studio exposes provider/voice selection. Unsupported provider/voice combinations are rejected by the backend.
- Free TTS contributes zero to the optional TTS cost estimate; STT/LLM costs remain operator-configured.

## Real network benchmark

Command:

```powershell
cd backend
uv run python scripts/benchmark_free_tts.py --repeats 2 --include-edge --output-dir D:\kira_ai\.tmp\free-tts-benchmark
```

Five prompt types were run twice: neutral Vietnamese, gaming slang, mixed Vietnamese/English terms, names/numbers/currency, and expressive punctuation.

| Provider / voice | Success | First PCM P50 | First PCM P95 | Signal integrity | Cancel dispatch |
|---|---:|---:|---:|---:|---:|
| gTTS `vi` | 10/10 (100%) | 332.978 ms | 440.630 ms | 100% | 0.109 ms |
| Edge Hoài My | 4/10 (40%) | 3538.569 ms | 6301.706 ms | 100% of successes | 0.254 ms |
| Edge Nam Minh | 8/10 (80%) | 3620.961 ms | 13846.639 ms | 100% of successes | 0.355 ms |

The first cold gTTS smoke request measured 1916.8 ms before the repeated benchmark. Edge failures were `NoAudioReceived`, retained as failed attempts rather than replaced by local fallback in the benchmark. Edge 7.3.0 produced no audio in both the adapter and its own CLI; 7.2.8 was therefore pinned, but its observed reliability still justifies the experimental flag.

Artifacts:

- `.tmp/free-tts-benchmark/benchmark.json`
- `.tmp/free-tts-benchmark/gtts-vi.wav`
- `.tmp/free-tts-benchmark/edge_experimental-vi-VN-HoaiMyNeural.wav`
- `.tmp/free-tts-benchmark/edge_experimental-vi-VN-NamMinhNeural.wav`

The WAV files are listening samples, not distributable project media. A human must record clarity/naturalness judgments before those checks can be marked PASS.

## Automated verification

| Command | Result |
|---|---|
| `uv run ruff check app tests` | PASS |
| `uv run mypy app` | PASS - 48 source files |
| `uv run ty check app` | PASS |
| `uv run pytest -q` | PASS - 118 tests, 76 warnings |
| `npx -y bun@1.3.12 run lint` | PASS - 89 files |
| `npx -y bun@1.3.12 run build` | PASS - known lazy 3D chunk warning only |
| Targeted free-TTS + diagnostics Playwright | PASS - 3/3 |
| Full Playwright Chromium suite with Mailpit | PASS - 66/66 in 2.0 minutes |
| `uv lock --check` | PASS - 152 packages resolved |
| `pip-audit --path D:\kira_ai\.venv\Lib\site-packages` | PASS - no known vulnerabilities; local non-PyPI `app` skipped |
| `npx -y bun@1.3.12 audit` | PASS - no vulnerabilities |
| Frontend/provider-secret pattern scan | PASS |
| `python harness/validate_pack.py` | PASS - documentation, 6 skills, 8 fixtures |

The first targeted Playwright attempt used `127.0.0.1`, which did not match the configured frontend origin and timed out in auth setup. The first new UI-test attempt then accessed `localStorage` before navigation and was fixed by visiting `/studio` first. The final targeted and full suites passed without skips or weakened assertions.

## Remaining blockers

1. Listen to the three WAVs and score pronunciation, slang, prosody and naturalness.
2. Run a credentialed Deepgram + OpenAI microphone session to measure full end-of-turn latency; TTS-only first PCM is not end-to-end latency.
3. Run the selected provider through the actual OBS Browser Source and verify audible exactly-once playback, routing, transparency and lip-sync.
4. Treat gTTS and Edge as best-effort online endpoints. Google Chirp remains the supported credentialed option when an SLA is required.
