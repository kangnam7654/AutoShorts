# Refactoring: Shared Utilities Extraction

> **Status: COMPLETED** — `tts_utils.py`, `ffmpeg_utils.py` 구현 완료. 테스트 포함 (91% coverage).

## Problem

compose.py, narrate.py, pipeline.py, finalize.py에 동일하거나 거의 동일한 함수들이 중복 정의되어 있음.
코드 변경 시 여러 파일을 동시에 수정해야 하고, 미처 빠뜨릴 위험이 높음.

## Duplicate Function Map

| Function | compose.py | narrate.py | pipeline.py | finalize.py | Status |
|----------|-----------|-----------|------------|------------|--------|
| `_tts()` | O | O (superset) | O | - | narrate.py가 clone 지원 추가 |
| `_tts_extension()` | O | - | O | - | 완전 동일 |
| `_default_voice()` | - | O | O | - | 코드 동일, 상수값 다름 |
| `_voice_prefix()` / `_voice_language_prefix()` | O | - | O | - | 완전 동일, 이름만 다름 |
| `_sentence_list()` / `_script_sentences()` | O | - | O | - | 거의 동일 |
| `_mux_video_audio()` / `_mux_video_with_audio()` | - | O | - | O | 완전 동일, 이름만 다름 |
| `_render_subtitled_video()` | O | - | - | O (superset) | finalize가 font_size/custom_font 추가 |

## Solution: 2개의 공유 모듈 생성

### 1. `Backend/tts_utils.py` — TTS 공통 유틸리티

**추출 대상:**
- `tts_generate(text, voice, filename, clone, ref_audio, ref_text, language)` — narrate.py 버전 기반 (superset)
- `tts_extension() -> str`
- `default_voice(purpose) -> str` — purpose별 기본 음성 (narration vs generation)
- `voice_language_prefix(voice) -> str`
- `split_sentences(script) -> list[str]` — compose.py 버전 기반 (더 robust)

**상수:**
- `TTS_PROVIDER` — 현재 각 파일에서 개별 로드
- `DEFAULT_VOICES` — dict로 통합: `{"narration": {"qwen": "Sohee", "tiktok": "kr_003"}, "generation": {"qwen": "Ryan", "tiktok": "en_us_001"}}`

### 2. `Backend/ffmpeg_utils.py` — FFmpeg 공통 유틸리티

**추출 대상:**
- `mux_video_audio(video_path, audio_path, output_path)` — finalize.py 버전 (docstring 포함)
- `render_subtitled_video(video_path, audio_path, subtitles_path, subs_position, subs_color, font_size, custom_font)` — finalize.py 버전 기반 (superset), font_size/custom_font 기본값 추가

## File Changes

### New Files
```
Backend/tts_utils.py    — TTS 공통 함수 5개 + 상수
Backend/ffmpeg_utils.py — FFmpeg 공통 함수 2개
```

### Modified Files (import 교체)
```
Backend/compose.py   — _tts, _tts_extension, _voice_prefix, _sentence_list, _render_subtitled_video 제거 → import
Backend/narrate.py   — _tts, _default_voice, _mux_video_with_audio 제거 → import
Backend/pipeline.py  — _tts, _tts_extension, _default_voice, _voice_language_prefix, _script_sentences 제거 → import
Backend/finalize.py  — _mux_video_audio, _render_subtitled_video 제거 → import
```

### Test Files (import 경로 업데이트)
```
tests/test_compose.py
tests/test_narrate.py
tests/test_finalize.py
tests/test_integration.py
```

### New Test Files
```
tests/test_tts_utils.py
tests/test_ffmpeg_utils.py
```

## API Design

### tts_utils.py

```python
"""Shared TTS utilities: provider routing, voice defaults, text splitting."""

TTS_PROVIDER: str          # "qwen" | "tiktok"

DEFAULT_VOICES = {
    "narration": {"qwen": "Sohee", "tiktok": "kr_003"},
    "generation": {"qwen": "Ryan", "tiktok": "en_us_001"},
}

def tts_generate(
    text: str,
    voice: str,
    filename: str,
    clone: bool = False,
    ref_audio: str = "",
    ref_text: str = "",
    language: str = "ko",
) -> None: ...

def tts_extension() -> str: ...

def default_voice(purpose: str = "generation") -> str: ...

def voice_language_prefix(voice: str) -> str: ...

def split_sentences(script: str) -> list[str]: ...
```

### ffmpeg_utils.py

```python
"""Shared FFmpeg utilities: muxing, subtitle rendering."""

def mux_video_audio(video_path: str, audio_path: str, output_path: str) -> None: ...

def render_subtitled_video(
    video_path: str,
    audio_path: str,
    subtitles_path: str,
    subs_position: str = "center,bottom",
    subs_color: str = "#FFFFFF",
    font_size: int = 100,
    custom_font: str = "",
) -> str: ...
```

## Migration Strategy

1. 새 모듈 생성 (`tts_utils.py`, `ffmpeg_utils.py`)
2. 새 모듈 테스트 작성 (`test_tts_utils.py`, `test_ffmpeg_utils.py`)
3. 기존 파일에서 중복 함수 제거 + import 교체 (한 파일씩)
4. 각 단계마다 `uv run python -m pytest tests/ -q` 전체 통과 확인
5. 기존 테스트 파일의 mock 경로 업데이트

## Non-Goals

- `_render_tts_audio()`: compose.py와 pipeline.py 버전이 본질적으로 다른 함수 (시그니처, 반환값, 책임 범위 모두 다름). 통합하지 않고 각자 유지하되, 내부에서 `tts_utils.tts_generate()`를 호출하도록만 변경.
- 콜백 네이밍 통일 (`emit` vs `on_log`): 이번 스코프에서 제외. 별도 PR로 처리.
- moviepy import 스타일 통일: cosmetic이므로 제외.
