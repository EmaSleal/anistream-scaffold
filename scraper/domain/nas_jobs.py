"""NAS job orchestration — no Flask import.

Wraps all HTTP communication with the NAS (disk-api-skeleton).  Every public
function is fail-open: network errors and unexpected status codes degrade
gracefully to safe defaults rather than raising to callers.
"""

import logging
import requests
from config import NAS_BASE_URL, NAS_API_KEY

logger = logging.getLogger(__name__)

_TIMEOUT = 5


class NasUnavailable(Exception):
    """Raised when the NAS is unreachable or returns a server error."""


def nas_configured() -> bool:
    return bool(NAS_BASE_URL and NAS_API_KEY)


def check_episode_status(series_id: str, episode_number: int) -> str:
    """Return 'downloaded', 'missing', or 'unknown'.

    'unknown' is returned on any network or unexpected error so callers can
    always render a result — mirrors the fail-open pattern of resolve_nas_stream.
    """
    if not nas_configured():
        return "unknown"

    try:
        resp = requests.get(
            f"{NAS_BASE_URL}/api/episodes/{series_id}/{episode_number}",
            headers={"X-API-Key": NAS_API_KEY},
            timeout=_TIMEOUT,
        )
    except Exception:
        logger.warning(
            "[nas_jobs] NAS unreachable for check_episode_status series=%s ep=%s",
            series_id,
            episode_number,
        )
        return "unknown"

    if resp.status_code == 404:
        return "missing"
    if resp.ok:
        return "downloaded"

    logger.warning(
        "[nas_jobs] unexpected NAS status %s for series=%s ep=%s",
        resp.status_code,
        series_id,
        episode_number,
    )
    return "unknown"


def create_download_job(
    series_id: str, episode_number: int, source_url: str, source: str
) -> dict:
    """POST /api/jobs to the NAS and return {jobId, status}.

    Raises NasUnavailable when the NAS is unreachable or returns 5xx.
    """
    if not nas_configured():
        raise NasUnavailable("NAS is not configured")

    payload = {
        "url": source_url,
        "category": "videos",
        "series_id": series_id,
        "episode_number": episode_number,
    }

    try:
        resp = requests.post(
            f"{NAS_BASE_URL}/api/jobs",
            headers={"X-API-Key": NAS_API_KEY, "Content-Type": "application/json"},
            json=payload,
            timeout=_TIMEOUT,
        )
    except Exception as exc:
        logger.warning("[nas_jobs] NAS unreachable for create_download_job: %s", exc)
        raise NasUnavailable("NAS unreachable") from exc

    if not resp.ok:
        logger.warning(
            "[nas_jobs] NAS rejected job with status %s: %s",
            resp.status_code,
            resp.text[:200],
        )
        raise NasUnavailable(f"NAS returned {resp.status_code}")

    data = resp.json()
    return {
        "jobId": data.get("job_id") or data.get("jobId", ""),
        "status": data.get("status", "pending"),
    }


def get_job_status(job_id: str) -> dict:
    """GET /api/jobs/{job_id} from the NAS.

    Always returns a dict with at least {"status": ...}.  Returns
    {"status": "unknown"} when the NAS is unreachable or returns 404.
    """
    if not nas_configured():
        return {"status": "unknown"}

    try:
        resp = requests.get(
            f"{NAS_BASE_URL}/api/jobs/{job_id}",
            headers={"X-API-Key": NAS_API_KEY},
            timeout=_TIMEOUT,
        )
    except Exception:
        logger.warning("[nas_jobs] NAS unreachable for get_job_status job_id=%s", job_id)
        return {"status": "unknown"}

    if resp.status_code == 404:
        return {"status": "unknown"}

    if not resp.ok:
        logger.warning(
            "[nas_jobs] NAS error %s for get_job_status job_id=%s",
            resp.status_code,
            job_id,
        )
        return {"status": "unknown"}

    data = resp.json()
    result: dict = {"status": data.get("status", "unknown")}
    if data.get("error"):
        result["error"] = data["error"]
    return result
