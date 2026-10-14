# 06 — Voice pipeline, latency & audio routing

## Targets (engineering, not vendor SLA)

- **P50 ≤2.5s / P95 ≤5s**: from streamer end-of-turn (VAD-confirmed) to AI first audible sample in OBS Browser Source.
- UI hard Mute → browser audio node `stop()` almost instant; target <200ms local, measured.
- No regressions from repeated chat, reconnect, or session hours-long memory.
- Speech quality in Vietnamese and game slang matters more than isolated synthetic speed demos.

## Recommended pipeline

```text
getUserMedia(input mic only)
 → AudioContext / AudioWorklet (PCM16 mono; 16kHz)
 → local Silero VAD gate + pre-roll buffer
 → WS binary audio frames
 → Deepgram Nova-3 Streaming STT adapter (or configured alternative)
 → partial/final transcript + turn end
 → Conversation Director
 → FPT Marketplace Chat Completions or OpenAI Responses streaming (model ID configurable)
 → sentence/clause segmentation
 → TTS streaming adapter (Google Chirp 3 HD vi-VN or alternative)
 → WS PCM audio chunks to OBS overlay
 → WebAudio single player + Three-VRM mouth amplitude
```

## Mic vs game audio

- Browser `getUserMedia({audio:{deviceId,echoCancellation:true,noiseSuppression:true,autoGainControl:...}})` captures mic endpoint only, not OBS Desktop Audio.
- Nếu dùng loa ngoài, game và giọng AI **vẫn có thể lọt vào mic vật lý**. Hướng dẫn sử dụng tai nghe + mic riêng; không quảng cáo “AI tự tách tuyệt đối”.
- Có audio device selector, input level meter và mic test recording local (opt-in, không upload nếu không cần).
- Streamer voice và AI TTS outputs tách rời; dashboard không phát âm thanh AI khi LIVE để tránh feedback.

## Streaming implementation details

### Audio capture

- Dùng AudioWorklet, không phụ thuộc ScriptProcessorNode deprecated.
- Audio frames target 20ms, PCM signed 16-bit mono 16kHz; validate provider expects đúng encoding/sample rate; resample khi source khác.
- VAD chạy local, pre-roll 150–300ms. Hysteresis + hangover chờ 300–600ms và adaptive threshold sau benchmark.
- Browser tab throttle/sleep không bảo đảm trong background trên mọi hệ điều hành; dashboard hiển thị cảnh báo và reconnect, không tự hứa luôn nghe khi tab đóng.

### STT

- Default Deepgram Nova-3 `language=vi` (kiểm tra SDK/WS API lúc code); configure interim/final results + endpointing.
- `partial` update short-term context nhưng **không được gửi thành câu trả lời cuối** cho user nếu chưa stable.
- Nếu STT mất mạng, báo degraded, không fake rằng vẫn hiểu streamer. Điều phối chat/paid còn hoạt động nếu các provider khác ổn.
- STT provider adapter interface:

```python
class SttAdapter(Protocol):
    async def start(self, config: SttConfig) -> None: ...
    async def send_pcm(self, frame: bytes) -> None: ...
    async def events(self) -> AsyncIterator[SttEvent]: ...
    async def close(self) -> None: ...
```

### LLM

- Response text stream; generate 1–2 sentences, brevity. Ưu tiên `reasoning.effort=none/low` khi model hỗ trợ và chất lượng đủ (không giả định setting hoạt động trên mọi model/endpoint).
- Tách text theo punctuation/completed phrase để gửi TTS sớm; **không phát từng token lẻ** (sẽ gây méo nhịp).
- If not enough text, wait a short bounded interval. Avoid voice speaking half a word when generation cancelled.

### TTS

- Google Chirp 3 HD hỗ trợ Vietnamese `vi-VN` và bidirectional streaming theo tài liệu; config voice ID env; validate API output encoding and sample rate.
- gTTS `vi` là lựa chọn online không cần credential. Adapter giữ MP3 trong memory, decode/resample bằng PyAV sang PCM16 mono 24 kHz, không ghi file. Vì gTTS không stream PCM, `tts_first_audio_ms` bao gồm toàn bộ request + decode của từng clause.
- Edge TTS `vi-VN-HoaiMyNeural`/`vi-VN-NamMinhNeural` là tùy chọn experimental, disabled mặc định. Nó dùng endpoint Edge không chính thức, retry một lần khi không nhận audio, rồi đi qua degraded local fallback. Không coi keyless là offline hoặc SLA.
- Text chunks: 1 phrase đủ phát tự nhiên, TTS provider yêu cầu config frame đầu. PCM playback buffer đủ nhỏ để không drop nhưng không giữ >1–2s khi cần barge-in (giá trị cần test).
- TTS adapter:

```python
class TtsAdapter(Protocol):
    async def synthesize_stream(self, text_chunks: AsyncIterator[str], voice: str) -> AsyncIterator[AudioChunk]: ...
    async def cancel(self, utterance_id: str) -> None: ...
```

- `AudioChunk`: `format=pcm_s16le`, `sample_rate_hz`, `channels=1`, `data`, `chunk_index`, `utterance_id`.
- Khi TTS real có sample rate khác, resample ở một điểm xác định, không dựa vào tốc độ mặc định browser.
- Mọi provider đều kết thúc ở cùng contract PCM16; overlay, single-audio-owner, lip-sync amplitude, generation/TTL và `speech.cancel` không có nhánh riêng theo provider.

## OBS overlay audio

- Một `AudioContext` duy nhất, audio chunks xếp theo `utterance_id` và `chunk_index`, start khi đủ buffer nhỏ.
- `speech.cancel` → stop source nodes, clear scheduled chunks, mark utterance cancelled, clear mouth animation.
- `speech.end` không đồng nghĩa playback hoàn tất; gửi ACK completion sau khi audio thực phát xong.
- OBS Browser Source có thể có hành vi autoplay/audio monitoring khác Chrome; làm smoke test trong OBS thật.
- Đảm bảo giọng AI chỉ thu vào stream một lần. OBS Browser Source playback + OBS Monitor and Output cấu hình sai có thể echo/duplicate nếu Desktop Audio thu lại monitor.

## Latency instrumentation

Ghi timestamps qua `trace_id`, đồng hồ monotonic khi đo cùng máy và UTC correlation khi qua nhiều máy:

| Metric | Ý nghĩa |
|---|---|
| `t_vad_speech_end` | Phát hiện cuối lượt nói |
| `t_stt_final` | Final transcript sẵn sàng |
| `t_director_decision` | Decision made |
| `t_llm_first_token` | LLM chunk đầu |
| `t_tts_first_audio_chunk` | TTS audio chunk đầu |
| `t_overlay_received_first_chunk` | Overlay nhận chunk |
| `t_playback_first_sample` | Overlay bắt đầu phát audio |
| `t_mute_requested` / `t_audio_stopped` | Time to mute |

- End-to-end P50/P95 từ `t_vad_speech_end` tới `t_playback_first_sample`, thống kê riêng direct-call vs spontaneous/chat/paid; không so nhầm với YouTube viewer glass-to-glass latency.
- Tên metric implementation là `stt_final_ms` cho VAD-end receipt → final transcript và `voice_end_to_first_playback_ack_ms` cho VAD-end receipt → overlay playback-start ACK. Trace `DEGRADED_FALLBACK_LOCAL` không được đưa vào P50/P95 provider thật.
- Clock between server/client không đồng bộ hoàn hảo: đo bằng timestamp delta cùng process hoặc roundtrip time calibration, ghi rõ phương pháp; không trừ trực tiếp wall clock lệch nhau.
- Expose `trace_id`, `session_id`, `utterance_id` trong diagnostics (không kèm raw audio hay secrets).

## Edge cases

- Streamer nói liên tục hơn 10 phút: split theo voice turns; context summarization không làm nghẽn STT.
- Streamer bị ngắt mạng: drop unbounded buffered audio; reinit STT and notify status.
- Audio AI lọt mic: label known playback windows; barge-in detection needs human-speech confidence, not blindly cut on any amplitude.
- Token stream produces filler then cancels: đừng gửi 1–2 từ TTS; group meaningful chunks.
- Mute while buffering: immediately cancel queued audio and TTS, avoid playback on resume.
- Overlay reload mid-speech: no audio replay; AI may choose to start a **new** relevant utterance after reconnect, not resume old audio by default.

## Benchmark tiếng Việt (bắt buộc trước production)

- Test corpus 60–100 clips gồm giọng Bắc/Trung/Nam, nói nhanh/chậm, từ game Việt–Anh, cười nói, nền game/nhạc, tên nhân vật tùy chỉnh.
- STT metric WER/CER và hotword accuracy; TTS đo subjective clarity, name pronunciation, first audio latency, response fluency.
- Real OBS soak test 2–3 giờ với CPU/GPU/RAM, WS reconnect và 1000+ chat events simulated.

> **V2 reuse:** Phase 3 thử Pipecat processor/transport trước khi tự viết voice runtime; đo latency và interruption của luồng **dashboard mic đến OBS overlay** thực tế, không coi Pipecat là OBS tích hợp sẵn.
