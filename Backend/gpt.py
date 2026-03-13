import json
import os
import re
from typing import Any, List, Optional, Tuple

from dotenv import load_dotenv
from logstream import log

from utils import ENV_FILE

load_dotenv(ENV_FILE)

AI_PROVIDER = os.getenv("AI_PROVIDER", "ollama").strip().lower()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
OLLAMA_TIMEOUT = float(os.getenv("OLLAMA_TIMEOUT", "180"))

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

CODEX_BASE_URL = "https://chatgpt.com/backend-api"
CODEX_RESPONSES_PATH = "/codex/responses"

KNOWN_CODEX_MODELS = [
    "gpt-5.4",
    "gpt-5.3-codex",
    "gpt-5.2-codex",
    "gpt-5.2",
    "gpt-5.1-codex",
    "gpt-5.1-codex-mini",
    "gpt-5.1",
    "gpt-5",
]

TITLE_SKIP_PHRASES = [
    "option",
    "here are",
    "recommendation",
    "tip",
    "key element",
    "to help",
    "could you",
    "what's the",
    "categorized",
    "more descriptive",
    "short &",
    "intriguing",
]

DESCRIPTION_SKIP_PHRASES = [
    "option ",
    "here are",
    "key element",
    "to help me",
    "could you tell",
    "what's the overall",
    "---",
]


def _openai_client():
    from openai import OpenAI

    if AI_PROVIDER == "codex":
        from codex_auth import get_access_token

        token = get_access_token()
        return OpenAI(api_key=token, base_url=CODEX_BASE_URL)

    if AI_PROVIDER == "openai":
        if not OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is not set. Add it to .env.")
        return OpenAI(api_key=OPENAI_API_KEY)

    raise RuntimeError(f"Unknown AI_PROVIDER for OpenAI client: {AI_PROVIDER}")


def _ollama_client():
    from ollama import Client

    return Client(host=OLLAMA_BASE_URL, timeout=OLLAMA_TIMEOUT)


def _pick_default_model(model_names: List[str], configured_model: str) -> str:
    if configured_model in model_names:
        return configured_model
    if model_names:
        return model_names[0]
    return configured_model


def _extract_ollama_model_name(model: Any) -> str:
    if hasattr(model, "model") and getattr(model, "model"):
        return str(getattr(model, "model")).strip()
    if hasattr(model, "name") and getattr(model, "name"):
        return str(getattr(model, "name")).strip()
    if isinstance(model, dict):
        return str(model.get("model") or model.get("name") or "").strip()
    return ""


def _extract_ollama_response_text(response: Any) -> str:
    content = ""
    message = getattr(response, "message", None)
    if message is not None:
        if hasattr(message, "content") and getattr(message, "content"):
            content = str(getattr(message, "content")).strip()
        elif isinstance(message, dict):
            content = str(message.get("content") or "").strip()

    if content:
        return content

    if hasattr(response, "response") and getattr(response, "response"):
        return str(getattr(response, "response")).strip()

    if isinstance(response, dict):
        return (
            str(response.get("message", {}).get("content") or "")
            or str(response.get("response") or "")
        ).strip()

    return ""


def _resolve_text_response(content: str, provider_name: str) -> str:
    cleaned = (content or "").strip()
    if not cleaned:
        raise RuntimeError(f"{provider_name} returned an empty response.")
    return cleaned


def _build_script_prompt(
    video_subject: str,
    paragraph_number: int,
    voice: str,
    custom_prompt: str,
) -> str:
    if custom_prompt:
        base_prompt = custom_prompt
    else:
        base_prompt = """
            Generate a script for a video, depending on the subject of the video.

            The script is to be returned as a string with the specified number of paragraphs.

            Here is an example of a string:
            "This is an example string."

            Do not under any circumstance reference this prompt in your response.

            Get straight to the point, don't start with unnecessary things like, "welcome to this video".

            Obviously, the script should be related to the subject of the video.

            YOU MUST NOT INCLUDE ANY TYPE OF MARKDOWN OR FORMATTING IN THE SCRIPT, NEVER USE A TITLE.
            YOU MUST WRITE THE SCRIPT IN THE LANGUAGE SPECIFIED IN [LANGUAGE].
            ONLY RETURN THE RAW CONTENT OF THE SCRIPT. DO NOT INCLUDE "VOICEOVER", "NARRATOR" OR SIMILAR INDICATORS OF WHAT SHOULD BE SPOKEN AT THE BEGINNING OF EACH PARAGRAPH OR LINE. YOU MUST NOT MENTION THE PROMPT, OR ANYTHING ABOUT THE SCRIPT ITSELF. ALSO, NEVER TALK ABOUT THE AMOUNT OF PARAGRAPHS OR LINES. JUST WRITE THE SCRIPT.
        """

    return f"""{base_prompt}

    Subject: {video_subject}
    Number of paragraphs: {paragraph_number}
    Language: {voice}

    """


def _clean_script_response(response: str, paragraph_number: int) -> str:
    cleaned = response.replace("*", "").replace("#", "")
    cleaned = re.sub(r"\[.*\]", "", cleaned)
    cleaned = re.sub(r"\(.*\)", "", cleaned)

    paragraphs = cleaned.split("\n\n")
    selected_paragraphs = paragraphs[:paragraph_number]
    log(f"Number of paragraphs used: {len(selected_paragraphs)}", "success")
    return "\n\n".join(selected_paragraphs)


def _build_search_terms_prompt(video_subject: str, amount: int, script: str) -> str:
    return f"""
    Generate {amount} search terms for stock videos,
    depending on the subject of a video.
    Subject: {video_subject}

    The search terms are to be returned as
    a JSON-Array of strings.

    Each search term should consist of 1-3 words,
    always add the main subject of the video.

    YOU MUST ONLY RETURN THE JSON-ARRAY OF STRINGS.
    YOU MUST NOT RETURN ANYTHING ELSE.
    YOU MUST NOT RETURN THE SCRIPT.

    The search terms must be related to the subject of the video.
    Here is an example of a JSON-Array of strings:
    ["search term 1", "search term 2", "search term 3"]

    For context, here is the full text:
    {script}
    """


def _parse_list_of_strings(response: str) -> List[str]:
    try:
        parsed = json.loads(response)
        if isinstance(parsed, list) and all(isinstance(term, str) for term in parsed):
            return parsed
        raise ValueError("Response is not a list of strings.")
    except (json.JSONDecodeError, ValueError):
        log("[*] GPT returned an unformatted response. Attempting to clean...", "warning")

    match = re.search(r"\[[\s\S]*\]", response)
    if match:
        try:
            parsed = json.loads(match.group())
            if isinstance(parsed, list) and all(isinstance(term, str) for term in parsed):
                return parsed
        except json.JSONDecodeError:
            pass

    quoted_terms = re.findall(r'"([^"\\]*(?:\\.[^"\\]*)*)"', response)
    return [term.strip() for term in quoted_terms if term.strip()]


def _build_title_prompt(video_subject: str) -> str:
    return f"""
    Generate a catchy and SEO-friendly title for a YouTube shorts video about {video_subject}.
    YOU MUST RETURN ONLY THE TITLE TEXT, NOTHING ELSE.
    NO markdown, NO lists, NO explanations. Just one single title under 100 characters.
    """


def _clean_title_line(line: str) -> str:
    return line.strip().strip("*#`\"'•-\u2013\u20141234567890. ")


def _should_skip_title_line(line: str) -> bool:
    lower = line.lower()
    return any(phrase in lower for phrase in TITLE_SKIP_PHRASES)


def _pick_title(raw_title: str, fallback: str) -> str:
    for line in raw_title.splitlines():
        cleaned = _clean_title_line(line)
        if not cleaned or len(cleaned) > 100:
            continue
        if _should_skip_title_line(cleaned):
            continue
        return cleaned[:100]
    return fallback[:100]


def _build_description_prompt(video_subject: str, script: str) -> str:
    return f"""
    Write a brief and engaging description for a YouTube shorts video about {video_subject}.
    The video is based on the following script:
    {script}
    YOU MUST RETURN ONLY THE DESCRIPTION TEXT, NOTHING ELSE.
    NO markdown formatting, NO multiple options. Just one short description under 500 characters.
    """


def _should_skip_description_line(line: str) -> bool:
    lower = line.lower()
    return any(phrase in lower for phrase in DESCRIPTION_SKIP_PHRASES)


def _pick_description(raw_description: str, fallback: str) -> str:
    description_lines = []
    for line in raw_description.splitlines():
        cleaned = line.strip()
        if _should_skip_description_line(cleaned):
            if description_lines:
                break
            continue
        if cleaned:
            description_lines.append(re.sub(r"[*#`]", "", cleaned))

    if not description_lines:
        return fallback
    return "\n".join(description_lines)[:5000]


def _build_archive_section(archive_context: str) -> str:
    if not archive_context:
        return ""

    return f"""
## PREVIOUS VIDEOS (avoid repeating same subject+character combos)
{archive_context}

Pick a DIFFERENT character, setting, or angle from the ones above.
"""


def _build_veo_structure_lines(num_parts: int) -> str:
    lines = [
        "- Part 1 (0-8s): Hook — mysterious opening that grabs attention, introduce the fortune teller character",
        "- Part 2 (8-16s): Core — deliver the main fortune/horoscope reading with specific details",
    ]
    if num_parts >= 3:
        lines.append("- Part 3 (16-24s): Closing — final advice + encourage subscription")
    for index in range(4, num_parts + 1):
        start = (index - 1) * 8
        end = index * 8
        lines.append(f"- Part {index} ({start}-{end}s): Continue the reading")
    return "\n".join(lines)


def _build_veo_prompt(subject: str, num_parts: int, archive_context: str) -> str:
    archive_section = _build_archive_section(archive_context)
    structure_lines = _build_veo_structure_lines(num_parts)

    return f"""You are a YouTube Shorts script writer and Veo 3 prompt engineer.
Create a {num_parts}-part video script (each part = 8 seconds, total = {num_parts * 8} seconds).
The character speaks the dialogue DIRECTLY in the video. Veo 3 generates the voice with lip sync.

SUBJECT: {subject}
{archive_section}
## STRUCTURE
{structure_lines}

## VEO PROMPT RULES (MUST FOLLOW)
1. ABSOLUTELY NO rendered text, titles, subtitles, captions, watermarks, or any on-screen writing. Veo cannot render text correctly. Subtitles will be added in post-processing. Repeat "no text, no titles, no subtitles, no captions, no watermarks" in every prompt.
2. ABSOLUTELY NO phone frames, device mockups, app UI, or screen borders. The video IS the content — it must look like a raw cinematic shot, NOT a screen recording or phone preview. Never mention "smartphone screen" in the prompt.
3. No background music. Ambient room sound only (candle crackle, cloth movement, faint metal sounds, incense ambience). No cuts. No transitions.
4. The character MUST speak the dialogue naturally in Korean. Include the EXACT dialogue text in the prompt inside an "Exact spoken Korean dialogue:" block.
5. VERTICAL format — always include "vertical 9:16 aspect ratio" at the start of the prompt.
6. SPECIFIC visuals — describe location, character appearance (clothing, hair, age), lighting, camera movement concretely. One uninterrupted elegant long take.
7. The "prompt" field is mostly English, but the dialogue block inside it is Korean. Korean text also goes in the separate "dialogue" field for subtitle generation.
8. MYSTICAL ATMOSPHERE is essential — use supernatural/occult/ethereal visual elements: glowing runes, floating particles, candlelight, smoke, crystal balls, tarot cards, celestial motifs, ancient scrolls, mystical symbols. The setting should feel otherworldly and enchanting.
9. Characters should be deeply mystical: ancient sorcerer, ethereal oracle, shadowy fortune teller surrounded by magical artifacts. NOT modern/casual settings.
10. VOICE must match the character's visible age, gender, and appearance. Describe the voice in terms that match the face: e.g. a middle-aged male with deep eyes → "a deep, calm, weathered male voice matching his age and appearance". Never let the voice description contradict the character's visible traits.
11. VOICE & LIP SYNC instructions must appear AFTER the dialogue block: "He/She must speak the dialogue naturally in Korean, with a [voice matching character appearance] voice, slow pacing, and short pauses between lines. Natural Korean lip sync. Clear mouth movement matched to Korean syllables. No subtitles. No on-screen text. No translation. No English speech. Ambient room sound stays soft under the voice."
12. Camera choreography: stable anatomy, stable hands, consistent face, controlled cinematic motion. The camera keeps moving in one uninterrupted elegant long take, slowly circling and pushing in.
13. The character is the ONLY speaker. No other voices. No narrator.

## DIALOGUE CONTENT RULES
- The dialogue must contain ACTUAL horoscope/fortune content: specific advice about wealth, relationships, career, health, lucky numbers, colors, directions.
- Do NOT use generic catchphrases. Each part should deliver real fortune-telling content.
- Write dialogue as SHORT separate lines with natural pauses, NOT one long sentence. Example:
  "오늘의 사주를 보면,\n지금은 들어오는 복보다\n새는 기운을 먼저 막아야 할 때입니다."
- Part 1: Hook with a dramatic opening fortune statement.
- Part 2: Detailed reading — mention specific areas of life (재물운, 애정운, 건강운 etc.) with concrete advice.
- Part 3: Final wisdom + call to action.

## OUTPUT FORMAT
Return ONLY a JSON array. No markdown, no explanation.

[
  {{
    "prompt": "Vertical 9:16 aspect ratio. Inside a dim mystical [setting description]. A [character description with age, gender, hair, clothing] stands/sits behind [props]. [Lighting and atmosphere]. [Camera movement — one uninterrupted long take]. No text, no titles, no subtitles, no captions, no watermarks. No phone frames or device borders.\\n\\nExact spoken Korean dialogue:\\n\\"한국어 대사 line 1,\\n한국어 대사 line 2,\\n한국어 대사 line 3.\\"\\n\\nHe/She must speak the dialogue naturally in Korean, with a [voice that matches the character's visible age and gender] voice, slow pacing, and short pauses between lines. Natural Korean lip sync. Clear mouth movement matched to Korean syllables. No subtitles. No on-screen text. No translation. No English speech. Ambient room sound stays soft under the voice. No music. No other voices.\\n\\nStyle: cinematic realism, grounded supernatural atmosphere, Korean mystical fortune-teller aesthetic, stable face, stable lip sync, realistic lighting, rich texture, elegant slow camera choreography.",
    "dialogue": "한국어 대사 (subtitle용 — prompt 안의 대사와 동일한 텍스트)",
    "situation": "한국어 장면 설명",
    "voice_hint": "예: calm korean male fortune teller, low tone"
  }},
  {{
    "prompt": "Create a vertical 9:16 video for YouTube Shorts...",
    "dialogue": "한국어 대사",
    "situation": "한국어 장면 설명",
    "voice_hint": "동일 캐릭터 음성"
  }}
]
"""


def _parse_veo_parts(response: str) -> Optional[List[dict[str, Any]]]:
    try:
        parsed = json.loads(response)
        if isinstance(parsed, list) and all(isinstance(part, dict) for part in parsed):
            return parsed
    except json.JSONDecodeError:
        pass

    match = re.search(r"\[[\s\S]*\]", response)
    if not match:
        return None

    try:
        parsed = json.loads(match.group())
    except json.JSONDecodeError:
        return None

    if isinstance(parsed, list) and all(isinstance(part, dict) for part in parsed):
        return parsed
    return None


def _fallback_veo_parts(response: str) -> List[dict[str, str]]:
    log("Failed to parse Veo prompts from LLM response, using raw text.", "warning")
    return [
        {
            "prompt": response,
            "dialogue": "",
            "narration": "",
            "situation": "",
        }
    ]


def _build_subtitle_correction_prompt(srt_content: str, original_script: str) -> str:
    return f"""You are a subtitle proofreader. Below are two inputs:

1. ORIGINAL SCRIPT (the correct text that was spoken):
{original_script}

2. WHISPER SRT (auto-generated subtitles with timestamps — text may contain errors):
{srt_content}

Your task:
- Keep ALL timestamps exactly as they are. Do NOT change any timing.
- Compare each subtitle text with the original script.
- Replace any misrecognized words with the correct words from the original script.
- Keep the same SRT structure (numbered entries, timestamps, text).
- If Whisper split or grouped words differently from the script, that's fine — just fix the TEXT within each entry.
- Output ONLY the corrected SRT content. No explanations, no markdown.
"""


def list_models() -> Tuple[List[str], str]:
    """Return available model names and the configured default."""
    if AI_PROVIDER == "ollama":
        return _list_ollama_models()
    return _list_openai_models()


def _list_ollama_models() -> Tuple[List[str], str]:
    try:
        response = _ollama_client().list()
    except Exception as err:
        raise RuntimeError(f"Failed to fetch Ollama models: {err}") from err

    raw_models: List[Any] = []
    if hasattr(response, "models") and getattr(response, "models") is not None:
        raw_models = list(getattr(response, "models"))
    elif isinstance(response, dict):
        raw_models = response.get("models") or []

    model_names = []
    for model in raw_models:
        name = _extract_ollama_model_name(model)
        if name:
            model_names.append(name)

    unique_names = list(dict.fromkeys(model_names))
    return unique_names, _pick_default_model(unique_names, OLLAMA_MODEL)


def _list_openai_models() -> Tuple[List[str], str]:
    if AI_PROVIDER == "codex":
        return KNOWN_CODEX_MODELS, _pick_default_model(KNOWN_CODEX_MODELS, OPENAI_MODEL)

    try:
        client = _openai_client()
        response = client.models.list()
        model_names = sorted(
            [model.id for model in response.data if "gpt" in model.id or "codex" in model.id]
        )
        if not model_names:
            model_names = [OPENAI_MODEL]
        return model_names, _pick_default_model(model_names, OPENAI_MODEL)
    except Exception as err:
        log(f"Could not list OpenAI models: {err}", "warning")
        return [OPENAI_MODEL], OPENAI_MODEL


def generate_response(prompt: str, ai_model: str) -> str:
    """Generate a response from the configured AI provider."""
    if AI_PROVIDER == "ollama":
        return _generate_ollama(prompt, ai_model)
    return _generate_openai(prompt, ai_model)


def _generate_openai(prompt: str, ai_model: str) -> str:
    model_name = (ai_model or "").strip() or OPENAI_MODEL

    if AI_PROVIDER == "codex":
        return _generate_codex(prompt, model_name)

    try:
        client = _openai_client()
        response = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
        )
        return _resolve_text_response(response.choices[0].message.content, "OpenAI")
    except RuntimeError:
        raise
    except Exception as err:
        raise RuntimeError(f"OpenAI API error: {err}") from err


def _generate_codex(prompt: str, model_name: str) -> str:
    """Call ChatGPT backend API using Codex OAuth token."""
    import requests as _requests

    from codex_auth import get_access_token, get_account_id

    token = get_access_token()
    account_id = get_account_id()
    url = f"{CODEX_BASE_URL}{CODEX_RESPONSES_PATH}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "chatgpt-account-id": account_id,
        "OpenAI-Beta": "responses=experimental",
        "originator": "codex_cli_rs",
    }
    body = {
        "model": model_name,
        "instructions": "You are a helpful assistant. Follow the user's instructions precisely.",
        "input": [
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": prompt}],
            }
        ],
        "store": False,
        "stream": True,
    }

    try:
        response = _requests.post(url, json=body, headers=headers, timeout=180, stream=True)
    except Exception as err:
        raise RuntimeError(f"Codex API request failed: {err}") from err

    if response.status_code == 401:
        raise RuntimeError("Codex auth expired. Run `cli.py auth` again.")
    if response.status_code == 429:
        raise RuntimeError("Codex rate limit reached. Wait a moment and try again.")
    if response.status_code != 200:
        raise RuntimeError(f"Codex API error ({response.status_code}): {response.text[:500]}")

    content = ""
    for raw_line in response.iter_lines():
        line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
        if not line or not line.startswith("data: "):
            continue

        payload = line[6:]
        if payload == "[DONE]":
            break

        try:
            event = json.loads(payload)
        except json.JSONDecodeError:
            continue

        event_type = event.get("type", "")
        if event_type == "response.output_text.delta":
            content += event.get("delta", "")
            continue

        if event_type != "response.completed":
            continue

        response_obj = event.get("response", {})
        for item in response_obj.get("output", []):
            if item.get("type") != "message":
                continue
            for part in item.get("content", []):
                if part.get("type") == "output_text" and not content:
                    content = part.get("text", "")

    return _resolve_text_response(content, "Codex")


def _generate_ollama(prompt: str, ai_model: str) -> str:
    from ollama import ResponseError

    model_name = (ai_model or "").strip() or OLLAMA_MODEL

    try:
        client = _ollama_client()
        try:
            response = client.chat(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                stream=False,
            )
        except ResponseError as err:
            if err.status_code != 404:
                raise

            try:
                response = client.generate(model=model_name, prompt=prompt, stream=False)
            except ResponseError as fallback_err:
                if fallback_err.status_code == 404 and "not found" in str(fallback_err).lower():
                    available_models, _ = _list_ollama_models()
                    available = ", ".join(available_models) if available_models else "none"
                    raise RuntimeError(
                        f"Ollama model '{model_name}' is not installed. Available models: {available}. "
                        f"Install it with: ollama pull {model_name}"
                    ) from fallback_err
                raise
    except RuntimeError:
        raise
    except Exception as err:
        raise RuntimeError(f"Failed to connect to Ollama: {err}") from err

    content = _extract_ollama_response_text(response)
    return _resolve_text_response(content, "Ollama")


def generate_script(
    video_subject: str,
    paragraph_number: int,
    ai_model: str,
    voice: str,
    customPrompt: str,
) -> Optional[str]:
    """Generate a script for a video."""
    prompt = _build_script_prompt(
        video_subject=video_subject,
        paragraph_number=paragraph_number,
        voice=voice,
        custom_prompt=customPrompt,
    )
    response = generate_response(prompt, ai_model)
    log(response, "info")

    if not response:
        log("[-] GPT returned an empty response.", "error")
        return None

    return _clean_script_response(response, paragraph_number)


def get_search_terms(
    video_subject: str,
    amount: int,
    script: str,
    ai_model: str,
) -> List[str]:
    """Generate search terms for stock videos."""
    prompt = _build_search_terms_prompt(video_subject, amount, script)
    response = generate_response(prompt, ai_model)
    log(response, "info")

    search_terms = _parse_list_of_strings(response)
    log(f"\nGenerated {len(search_terms)} search terms: {', '.join(search_terms)}", "info")
    return search_terms


def generate_metadata(
    video_subject: str,
    script: str,
    ai_model: str,
) -> Tuple[str, str, List[str]]:
    """Generate metadata for a YouTube video."""
    raw_title = generate_response(_build_title_prompt(video_subject), ai_model).strip()
    raw_description = generate_response(
        _build_description_prompt(video_subject, script),
        ai_model,
    ).strip()

    title = _pick_title(raw_title, video_subject)
    description = _pick_description(raw_description, video_subject)
    keywords = get_search_terms(video_subject, 6, script, ai_model)
    return title, description, keywords


def _load_archive() -> List[dict]:
    """Load past Veo generation records from archive."""
    from utils import OUTPUT_DIR

    archive_path = OUTPUT_DIR / "archive.json"
    if not archive_path.exists():
        return []

    try:
        with open(archive_path, "r", encoding="utf-8") as file:
            return json.loads(file.read())
    except (json.JSONDecodeError, OSError):
        return []


def save_to_archive(subject: str, parts: List[dict]) -> None:
    """Append a generation record to the archive."""
    from datetime import datetime

    from utils import OUTPUT_DIR

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    archive_path = OUTPUT_DIR / "archive.json"

    archive = _load_archive()
    archive.append(
        {
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "subject": subject,
            "parts": parts,
        }
    )

    with open(archive_path, "w", encoding="utf-8") as file:
        file.write(json.dumps(archive, ensure_ascii=False, indent=2))


def _format_archive_for_prompt(archive: List[dict], max_entries: int = 10) -> str:
    """Format recent archive entries as context for the LLM."""
    recent_entries = archive[-max_entries:]
    if not recent_entries:
        return ""

    lines = []
    for entry in recent_entries:
        subject = entry.get("subject", "")
        date = entry.get("date", "")
        characters = set()
        for part in entry.get("parts", []):
            situation = part.get("situation", "")
            if situation:
                characters.add(
                    situation.split("이")[0][:20] if "이" in situation else situation[:20]
                )
        lines.append(f"- [{date}] {subject} (장면: {', '.join(characters) or 'N/A'})")
    return "\n".join(lines)


def generate_veo_prompts(subject: str, ai_model: str, num_parts: int = 3) -> List[dict]:
    """Generate multi-part Veo prompts for a YouTube Shorts video."""
    from workflow import normalize_parts

    archive = _load_archive()
    archive_context = _format_archive_for_prompt(archive)
    prompt = _build_veo_prompt(subject, num_parts, archive_context)

    response = generate_response(prompt, ai_model).strip()
    parts = _parse_veo_parts(response)
    if parts is None:
        parts = _fallback_veo_parts(response)

    normalized = normalize_parts(parts)
    save_to_archive(subject, normalized)
    return normalized


def correct_subtitles(srt_content: str, original_script: str, ai_model: str) -> str:
    """Correct subtitle text while preserving Whisper timing."""
    prompt = _build_subtitle_correction_prompt(srt_content, original_script)
    corrected = generate_response(prompt, ai_model).strip()

    if "-->" not in corrected:
        log("LLM correction failed validation, using original Whisper SRT.", "warning")
        return srt_content

    return corrected
