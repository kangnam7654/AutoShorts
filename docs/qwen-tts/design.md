# Qwen3-TTS Integration Design

## 목적
TikTok TTS를 Qwen3-TTS로 교체하여 안정성과 품질 향상.

## 현재 문제 (TikTok TTS)
- 세션 ID 만료 시 장애
- 제3자 프록시 서버 의존
- 300자 제한, fragile base64 파싱

## 솔루션
Apple Silicon(M1 Pro 16GB)에서 `mlx-audio` 패키지로 Qwen3-TTS 로컬 실행.

## 모델 선택
- `mlx-community/Qwen3-TTS-12Hz-0.6B-CustomVoice-bf16`
- RAM ~2-3GB, 로컬 실행, 오프라인 가능
- 9개 내장 음성 + 감정/스타일 제어

## 음성 목록 (CustomVoice)
| Speaker | Language |
|---------|----------|
| Ryan | English |
| Aiden | English |
| Vivian | Chinese |
| Serena | Chinese |
| Uncle_Fu | Chinese |
| Dylan | Chinese (Beijing) |
| Eric | Chinese (Sichuan) |
| Ono_anna | Japanese |
| Sohee | Korean |

## 아키텍처

```
pipeline.py
  └─ TTS_PROVIDER env var
       ├─ "tiktok" → tiktokvoice.tts()  (기존)
       └─ "qwen"  → qwen_tts.tts()     (신규)
```

## 파일 변경
| File | Action |
|------|--------|
| `Backend/qwen_tts.py` | 신규 생성 - mlx-audio 기반 TTS |
| `Backend/pipeline.py` | TTS_PROVIDER 분기 추가 |
| `Backend/cli.py` | voices 명령에 Qwen 음성 추가 |
| `.env` | TTS_PROVIDER 추가 |
| `pyproject.toml` | mlx-audio 의존성 추가 |

## qwen_tts.py 인터페이스
```python
VOICES = ["Ryan", "Aiden", "Vivian", "Serena", ...]

def tts(text: str, voice: str, filename: str) -> None:
    # 1. 모델 lazy load (싱글턴)
    # 2. generate_custom_voice() 호출
    # 3. WAV 파일로 저장
```

## 오디오 포맷
- Qwen3-TTS 출력: mx.array → numpy → soundfile로 WAV 저장
- moviepy AudioFileClip은 WAV 지원 → 호환 문제 없음
- pipeline.py에서 확장자 .wav 사용
