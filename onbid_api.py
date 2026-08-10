"""Shared client for the next-generation Onbid real-estate list API."""

import json
import time

import requests


URL = "https://apis.data.go.kr/B010003/OnbidRlstListSrvc2/getRlstCltrList2"
SUCCESS_CODES = {"00", "0", "200"}
NO_DATA_CODES = {"03"}
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 3
REQUEST_TIMEOUT = (10, 45)


class OnbidApiError(RuntimeError):
    """Raised when an Onbid request cannot produce a valid response."""


def _response_message(response):
    """Return a short error description without exposing the request URL/key."""
    try:
        data = response.json()
        if isinstance(data, dict) and "OpenAPI_ServiceResponse" in data:
            service_response = data.get("OpenAPI_ServiceResponse", {})
            common_header = (
                service_response.get("cmmMsgHeader", {})
                if isinstance(service_response, dict)
                else {}
            )
            if isinstance(common_header, dict):
                code = str(common_header.get("returnReasonCode", "")).strip()
                message = str(
                    common_header.get("returnAuthMsg")
                    or common_header.get("errMsg")
                    or ""
                ).strip()
                if code or message:
                    return f"API {code or '?'}: {message or '메시지 없음'}"

        root = data.get("response", data) if isinstance(data, dict) else {}
        header = root.get("header", root.get("result", {}))
        if isinstance(header, dict):
            code = str(header.get("resultCode", "")).strip()
            message = str(header.get("resultMsg", "")).strip()
            if code or message:
                return f"API {code or '?'}: {message or '메시지 없음'}"
    except (ValueError, TypeError, AttributeError):
        pass

    text = " ".join((response.text or "").split())
    return text[:300] or "응답 본문 없음"


def _extract_parts(data):
    if not isinstance(data, dict):
        raise OnbidApiError("API 응답이 JSON 객체가 아닙니다.")

    root = data.get("response", data)
    if not isinstance(root, dict):
        raise OnbidApiError("API 응답 구조를 해석할 수 없습니다.")

    header = root.get("header", root.get("result", {}))
    body = root.get("body", {})
    if not isinstance(header, dict):
        header = {}
    if not isinstance(body, dict):
        body = {}
    return header, body


def fetch_page(params, context, logger=print):
    """Fetch and validate one result page.

    Returns the response body, or ``None`` when the API reports no data.
    Authentication keys are deliberately never included in log messages.
    """
    last_error = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = requests.get(URL, params=params, timeout=REQUEST_TIMEOUT)
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
            last_error = f"연결 실패: {exc.__class__.__name__}"
            if attempt < MAX_ATTEMPTS:
                delay = 2 ** (attempt - 1)
                logger(f"  [재시도 {attempt}/{MAX_ATTEMPTS}] {context} - {last_error} ({delay}초 후)")
                time.sleep(delay)
                continue
            raise OnbidApiError(f"{context} - {last_error}") from exc
        except requests.exceptions.RequestException as exc:
            raise OnbidApiError(f"{context} - 요청 실패: {exc.__class__.__name__}") from exc

        if response.status_code in RETRYABLE_STATUS_CODES and attempt < MAX_ATTEMPTS:
            delay = 2 ** (attempt - 1)
            logger(
                f"  [재시도 {attempt}/{MAX_ATTEMPTS}] {context} - "
                f"HTTP {response.status_code} ({delay}초 후)"
            )
            time.sleep(delay)
            continue

        if response.status_code != 200:
            raise OnbidApiError(
                f"{context} - HTTP {response.status_code}: {_response_message(response)}"
            )

        try:
            data = response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise OnbidApiError(f"{context} - JSON 응답 해석 실패") from exc

        header, body = _extract_parts(data)
        result_code = str(header.get("resultCode", "")).strip()
        result_message = str(header.get("resultMsg", "")).strip()

        if result_code in NO_DATA_CODES:
            return None
        if result_code not in SUCCESS_CODES:
            raise OnbidApiError(
                f"{context} - API {result_code or '?'}: {result_message or '메시지 없음'}"
            )
        return body

    raise OnbidApiError(f"{context} - {last_error or '알 수 없는 요청 오류'}")
