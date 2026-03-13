# MoneyPrinter macOS App Design

## 목적
MoneyPrinter finalize 파이프라인을 감싸는 네이티브 macOS 앱.
.app 더블클릭 → 파일 드래그앤드롭 → 버튼 클릭 → 완성.

## 기술 스택
- **SwiftUI** (macOS 14+)
- 별도 서버 없음 — 내부적으로 `uv run python Backend/cli.py finalize ...` 서브프로세스 호출
- Xcode 프로젝트 없이 Swift Package로 빌드 가능

## UI 구성

```
┌─────────────────────────────────────┐
│  MoneyPrinter                    ─ □ x │
├─────────────────────────────────────┤
│                                     │
│  ┌───────────────────────────────┐  │
│  │  📹 영상을 여기에 드래그       │  │
│  │     veo_video.mp4             │  │
│  └───────────────────────────────┘  │
│                                     │
│  ┌───────────────────────────────┐  │
│  │  🎵 음악을 여기에 드래그       │  │
│  │     bgm.mp3 (선택)            │  │
│  └───────────────────────────────┘  │
│                                     │
│  ┌───────────────────────────────┐  │
│  │  📝 원본 스크립트 (선택)       │  │
│  │     (자막 검수용)              │  │
│  └───────────────────────────────┘  │
│                                     │
│  언어: [한국어 ▾]                   │
│  자막 크기: [55 ▾]                  │
│  9:16 크롭: [✓]                     │
│  음악 볼륨: [━━━━●━━] 10%           │
│                                     │
│  [ ▶ Finalize ]                     │
│                                     │
│  ┌───────────────────────────────┐  │
│  │ [1/6] Cropping to 9:16...     │  │
│  │ [2/6] Extracting audio...     │  │
│  │ [3/6] Generating subtitles... │  │
│  │ ...                           │  │
│  └───────────────────────────────┘  │
│                                     │
│  [ 📂 출력 폴더 열기 ]              │
│                                     │
└─────────────────────────────────────┘
```

## 동작 방식

1. 사용자가 영상/음악 파일을 드래그앤드롭 (또는 파일 선택)
2. 옵션 설정 (언어, 크롭, 폰트 사이즈, 볼륨)
3. "Finalize" 버튼 클릭
4. 앱이 `Process`로 CLI 호출:
   ```
   uv run python Backend/cli.py finalize \
     --video /path/to/video.mp4 \
     --music /path/to/music.mp3 \
     --language ko \
     --font-size 55 \
     --music-volume 0.10 \
     -o output/video_final.mp4
   ```
5. stdout를 실시간으로 로그 뷰에 표시
6. 완료 시 "출력 폴더 열기" 버튼 활성화

## 파일 구조

```
App/
├── Package.swift
└── Sources/
    └── MoneyPrinter/
        ├── MoneyPrinterApp.swift     # @main 엔트리포인트
        ├── ContentView.swift         # 메인 UI
        ├── DropZone.swift            # 드래그앤드롭 컴포넌트
        └── PipelineRunner.swift      # CLI 서브프로세스 실행
```

## 빌드/실행

```bash
cd App
swift build
swift run
# 또는 .app 번들 생성:
swift build -c release
```
