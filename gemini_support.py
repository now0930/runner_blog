"""Shared Gemini configuration and safe, actionable failures."""
import hashlib
import logging
import os
import random
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai

DEFAULT_MODEL = "gemini-3.8-flash"
logger = logging.getLogger(__name__)


class AnalysisError(RuntimeError):
    """An analysis failure that must never become a published post."""


def key_fingerprint(key):
    return hashlib.sha256(key.encode()).hexdigest()[:12]


def settings():
    load_dotenv(Path(__file__).with_name(".env"), override=False)
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key or key == "your_gemini_api_key":
        raise AnalysisError("GEMINI_API_KEY를 .env에 설정하세요.")
    model = os.getenv("AY_GEMINI_MODEL", "").strip() or DEFAULT_MODEL
    fallback = os.getenv("AY_GEMINI_FALLBACK_MODEL", "").strip()
    return key, model, fallback


def make_client(key):
    # Explicitly select the Developer API, even if Vertex environment vars exist.
    return genai.Client(api_key=key, vertexai=False,
                        http_options={"timeout": 60000,
                                      "retry_options": {"attempts": 1}})


def generate_with_retry(client, **kwargs):
    """Retry transient server failures, with four total attempts per model."""
    for attempt in range(4):
        try:
            return client.models.generate_content(**kwargs)
        except Exception as error:
            code = status_code(error)
            if code not in (500, 502, 503, 504) or attempt == 3:
                raise
            delay = 2 ** (attempt + 1) + random.uniform(0, 1)
            logger.warning("Gemini HTTP %s; retry %s/3 in %.1fs", code, attempt + 1, delay)
            time.sleep(delay)


def status_code(error):
    code = getattr(error, "code", None)
    if code is None:
        code = getattr(getattr(error, "response", None), "status_code", None)
    try:
        return int(code)
    except (TypeError, ValueError):
        return None


def safe_error(error):
    code = status_code(error)
    # Inspect raw details only to classify; never log or publish them.
    detail = str(error).lower()
    if code == 402 or (code == 429 and "prepay" in detail):
        return ("Gemini 결제 크레딧 부족(HTTP %s). https://ai.studio/projects 에서 "
                "이 키의 프로젝트와 연결된 결제 계정의 선불 잔액을 확인하세요. "
                "같은 결제 계정에 새 프로젝트를 만들어도 해결되지 않을 수 있습니다. "
                "키를 바꿨다면 컨테이너를 재생성하고 키 지문을 비교하세요.") % code
    if code in (400, 401, 403):
        return "Gemini 요청/인증 거부(HTTP %s). 키의 유효성, API 권한 및 요청 설정을 확인하세요." % code
    if code == 404:
        return "Gemini 모델을 사용할 수 없습니다(HTTP 404). AY_GEMINI_MODEL을 사용 가능한 모델로 변경하세요."
    if code == 429:
        return "Gemini 요청 한도 초과(HTTP 429). 프로젝트 할당량을 확인하고 나중에 재시도하세요."
    if code in (500, 502, 503, 504):
        return ("Gemini 서버 일시 오류(HTTP %s). 잠시 후 GPX를 다시 전송하세요. "
                "서비스 상태: https://aistudio.google.com/status") % code
    return "Gemini 호출 실패(HTTP %s). 네트워크와 서비스 상태를 확인하세요." % (code or "unknown")
