import logging
import time

import requests


logger = logging.getLogger(__name__)
TRANSIENT_STATUS_CODES = {500, 502, 503, 504}


class AiServiceError(RuntimeError):
    pass


class AiService:
    """Small OpenAI-compatible chat-completions client."""

    def __init__(
        self,
        api_key=None,
        base_url="https://api.openai.com/v1",
        model="gpt-4o-mini",
        timeout=20,
        max_retries=2,
        retry_backoff=0.25,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.max_retries = max(0, int(max_retries))
        self.retry_backoff = max(0.0, float(retry_backoff))

    def _wait_before_retry(self, attempt):
        delay = self.retry_backoff * (2**attempt)
        if delay:
            time.sleep(delay)

    def generate(self, system_instructions, user_prompt):
        if not self.api_key:
            raise AiServiceError("AI_SERVICE_API_KEY is not configured.")

        request_kwargs = {
            "headers": {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            "json": {
                "model": self.model,
                "temperature": 0.1,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system_instructions},
                    {"role": "user", "content": user_prompt},
                ],
            },
            "timeout": self.timeout,
        }
        for attempt in range(self.max_retries + 1):
            try:
                response = requests.post(
                    f"{self.base_url}/chat/completions", **request_kwargs
                )
            except (requests.Timeout, requests.ConnectionError) as exc:
                if attempt < self.max_retries:
                    logger.warning(
                        "AI request failed transiently; retrying (%s/%s).",
                        attempt + 1,
                        self.max_retries,
                    )
                    self._wait_before_retry(attempt)
                    continue
                if isinstance(exc, requests.Timeout):
                    raise AiServiceError("The AI service timed out after retries.") from exc
                raise AiServiceError(
                    "The AI service could not be reached after retries."
                ) from exc

            if response.status_code == 429:
                try:
                    error_code = response.json().get("error", {}).get("code")
                except (AttributeError, TypeError, ValueError):
                    error_code = None
                if error_code in ("credit_balance_exhausted", "insufficient_quota"):
                    raise AiServiceError(
                        "The AI service account has no credits remaining."
                    )
                raise AiServiceError("The AI service is temporarily rate limited.")

            if response.status_code in TRANSIENT_STATUS_CODES:
                if attempt < self.max_retries:
                    logger.warning(
                        "AI service returned HTTP %s; retrying (%s/%s).",
                        response.status_code,
                        attempt + 1,
                        self.max_retries,
                    )
                    self._wait_before_retry(attempt)
                    continue
                raise AiServiceError(
                    f"The AI service remained unavailable after retries "
                    f"(HTTP {response.status_code})."
                )

            try:
                response.raise_for_status()
                payload = response.json()
                return payload["choices"][0]["message"]["content"]
            except (
                requests.RequestException,
                KeyError,
                IndexError,
                TypeError,
                ValueError,
            ) as exc:
                raise AiServiceError(
                    "The AI service could not generate an outlook."
                ) from exc
