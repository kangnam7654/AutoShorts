# Veo 대사 직접 생성 (Dialogue-in-Prompt)

> **Status: COMPLETED** — Veo 3.1이 대사를 직접 생성. TTS 오버레이 기본 비활성화, `--add-narration`으로 fallback 가능.

## 목적

현재 Veo 파이프라인은 무음 영상을 생성한 뒤 TTS로 대사를 오버레이한다.
Veo 3는 프롬프트에 대사를 직접 포함하면 캐릭터가 립싱크와 함께 자연스럽게 말하는 영상을 생성할 수 있다.
TTS 오버레이를 제거하고, 대사를 Veo 프롬프트에 직접 임베딩하는 방식으로 전환한다.

## 변경 전/후 비교

### Before
```
LLM → Veo prompt (silent character) → 무음 영상
  → narrate.py (TTS 오버레이) → finalize.py (자막)
```

### After
```
LLM → Veo prompt (대사 포함) → 대사가 포함된 영상
  → finalize.py (자막만)
```

## 변경 대상 파일

### 1. `Backend/gpt.py` — `_build_veo_prompt()`

**현재**: prompt 규칙에 "NO dialogue audio, silent character" 강제
**변경**: 대사를 Veo prompt에 직접 포함하도록 지시

주요 변경:
- 규칙 2번 "NO narration, NO dialogue audio" → 삭제
- 규칙 3번 "character must NOT speak" → "character MUST speak the dialogue naturally"
- dialogue를 prompt 필드 안에 `Exact spoken Korean dialogue:` 블록으로 포함하도록 지시
- voice_hint를 prompt 안에 음성 특성으로 포함 (예: "low, calm, fortune-teller-like male voice")
- "Natural Korean lip sync. Clear mouth movement." 등 립싱크 지시 추가
- "No subtitles. No on-screen text." 유지 (자막은 post-processing)

출력 포맷 변경:
```json
{
  "prompt": "English Veo prompt with embedded dialogue block...\n\nExact spoken Korean dialogue:\n\"대사 내용\"\n\nHe must speak naturally in Korean with a low calm voice...",
  "dialogue": "한국어 대사 (자막용으로 별도 보관)",
  "narration": "",
  "situation": "장면 설명",
  "voice_hint": "calm korean male fortune teller"
}
```

### 2. `Backend/cli.py` — `veo()` 함수

**현재**: `--no-narration` 플래그로 수동 스킵
**변경**: 기본값을 narration 스킵으로 변경 (대사가 이미 영상에 포함)

- `--no-narration` 기본값 → `True` (대사가 Veo에 포함되므로)
- `--add-narration` 플래그 추가 (레거시 TTS 오버레이가 필요한 경우)

### 3. `Backend/workflow.py` — `extract_script()`

변경 없음. dialogue 필드는 그대로 유지되므로 자막 생성용 스크립트 추출은 동일하게 작동.

### 4. `Backend/veo.py`

변경 없음. prompt 문자열을 그대로 Veo API에 전달하므로, 대사가 포함된 긴 prompt도 그대로 작동.

## 프롬프트 예시 (LLM이 생성해야 하는 결과)

```
Create a vertical 9:16 video for YouTube Shorts, full-body composition...
[시각 묘사]

The camera begins close on a candle flame...
[카메라 움직임]

Exact spoken Korean dialogue:
"오늘의 사주를 보면,
지금은 들어오는 복보다
새는 기운을 먼저 막아야 할 때입니다."

He must speak the dialogue naturally in Korean, with a low, calm,
fortune-teller-like male voice, slow pacing, and short pauses between lines.
Natural Korean lip sync. Clear mouth movement matched to Korean syllables.
No subtitles. No on-screen text. No translation. No English speech.
Ambient room sound stays soft under the voice.
```

## 의사결정

| 항목 | 결정 | 이유 |
|------|------|------|
| dialogue 필드 유지 | O | 자막 생성 시 정확한 대사 텍스트 필요 |
| narration 필드 | 빈 문자열 | TTS 사용 안 함 |
| voice_hint 활용 | prompt에 음성 지시로 변환 | Veo가 음성 특성을 이해 |
| 기존 TTS 경로 보존 | O | `--add-narration`으로 fallback 가능 |
