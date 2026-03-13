# Output 디렉토리 구조 정리

## 목적

Veo 워크플로우의 산출물(생성 영상, 완성 영상, 프롬프트)을 용도별 폴더로 명확히 분리한다.

## 현재 구조 (문제점)

```
output/
├── archive.json
├── jeongbin_15s_final.mp4          ← 완성본이 루트에 섞임
├── raw/
│   ├── jeongbin_15s_v3.mp4         ← Veo 원본
│   ├── jeongbin_15s_prompts.json   ← 프롬프트가 raw에 섞임
│   └── jeongbin_15s_v3_subtitled_v7.mp4  ← 완성본이 raw에도 섞임
└── narrated/
    └── ...
```

- 프롬프트 JSON이 raw 영상과 같은 폴더에 있음
- finalize 결과물이 output/ 루트에 flat하게 쌓임
- 뭐가 원본이고 뭐가 완성본인지 구분 어려움

## 변경 후 구조

```
output/
├── archive.json                    # 생성 이력 메타데이터
├── raw/                            # Veo 생성 원본 영상만
│   ├── jeongbin_15s.mp4
│   ├── jeongbin_15s_part1.mp4
│   └── jeongbin_15s_part2.mp4
├── final/                          # 자막 씌운 완성 영상
│   └── jeongbin_15s.mp4
└── prompts/                        # 프롬프트 JSON
    └── jeongbin_15s.json
```

## 변경 대상

### 1. `utils.py` — 새 디렉토리 상수 추가

```python
FINAL_DIR = OUTPUT_DIR / "final"
PROMPTS_DIR = OUTPUT_DIR / "prompts"
```

### 2. `veo.py` — 프롬프트 저장 경로 변경

- 프롬프트 JSON 저장: `OUTPUT_DIR/raw/` → `PROMPTS_DIR/`
- raw 영상 저장: 변경 없음 (이미 `OUTPUT_DIR/raw/`)

### 3. `finalize.py` — 완성본 저장 경로 변경

- `_resolve_output_path()` 기본값: `OUTPUT_DIR/{stem}_final.mp4` → `FINAL_DIR/{stem}.mp4`
- `_final` 접미사 제거 (폴더로 구분되므로 불필요)

### 4. `cli.py` — `-o` 미지정 시 기본 경로 조정

- `finalize` 명령: 기본 출력을 `final/` 폴더로
- `veo` 명령: finalize 단계에서 자동으로 `final/`로 저장

### 5. `narrate.py` — narrated/ 유지 (기존 그대로)

- `OUTPUT_DIR/narrated/` 경로 유지
- 당분간 사용 안 하지만 코드는 남겨둠

### 6. 테스트 — mock 경로 업데이트

- `test_finalize.py`: OUTPUT_DIR mock이 `final/` 하위 경로를 반영하도록
- `test_integration.py`: 동일

## 마이그레이션

기존 파일은 수동 이동 (스크립트 불필요, 파일 3개뿐):
```bash
mkdir -p output/final output/prompts
mv output/raw/jeongbin_15s_prompts.json output/prompts/jeongbin_15s.json
mv output/raw/jeongbin_15s_v3_subtitled_v7.mp4 output/final/jeongbin_15s_v7.mp4
```
