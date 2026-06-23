"""Flask Blueprint for the AnimeAV1 / Zilla server-side proxy.

The Zilla player requires Referer: https://animeav1.com/ on every request
(manifest and segments). Browsers cannot set Referer freely, so all Zilla
traffic is routed through this endpoint.

Route:
    GET /api/stream/animeav1-proxy?path=<url-encoded-zilla-url>

Behavior:
    - Missing `path` → 400
    - Zilla 4xx/5xx → 502
    - .m3u8 / mpegurl content-type → rewrite every segment/variant line and
      every #EXT-X-KEY URI to point back through this proxy
    - All other content (`.ts`, binary segments) → stream bytes unchanged
"""

import re
import urllib.parse
import requests
from flask import Blueprint, request, Response, jsonify

stream_proxy_bp = Blueprint("stream_proxy", __name__)

_ZILLA_HEADERS = {
    "Referer": "https://animeav1.com/",
    "Origin": "https://animeav1.com",
}

_M3U8_CONTENT_TYPES = {
    "application/vnd.apple.mpegurl",
    "application/x-mpegurl",
    "audio/mpegurl",
    # Some servers return text/plain for m3u8 manifests
    "text/plain",
}

_PROXY_PATH = "/api/stream/animeav1-proxy"


def _is_m3u8(url: str, content_type: str) -> bool:
    """Heuristic: treat as HLS manifest if URL ends with .m3u8 or content-type matches."""
    if url.lower().split("?")[0].endswith(".m3u8"):
        return True
    base_ct = content_type.lower().split(";")[0].strip()
    return base_ct in _M3U8_CONTENT_TYPES


def _rewrite_m3u8(manifest_text: str, base_url: str) -> str:
    """Rewrite all non-comment lines and #EXT-X-KEY URI values to go through the proxy.

    Args:
        manifest_text: raw HLS manifest string.
        base_url: absolute URL of the manifest (used to resolve relative paths).

    Returns:
        Rewritten manifest string.
    """
    lines = manifest_text.splitlines(keepends=True)
    out = []
    for line in lines:
        stripped = line.rstrip("\r\n")
        newline = line[len(stripped):]

        if stripped.startswith("#EXT-X-KEY") and 'URI="' in stripped:
            # Rewrite the URI="..." value inside the tag
            def _rewrite_uri(m):
                raw_uri = m.group(1)
                absolute = urllib.parse.urljoin(base_url, raw_uri)
                encoded = urllib.parse.quote(absolute, safe="")
                return f'URI="{_PROXY_PATH}?path={encoded}"'

            rewritten = re.sub(r'URI="([^"]+)"', _rewrite_uri, stripped)
            out.append(rewritten + newline)

        elif stripped.startswith("#"):
            # Other comment/tag lines pass through unchanged
            out.append(line)

        elif stripped:
            # Segment URL or variant playlist line — resolve relative, then proxy
            absolute = urllib.parse.urljoin(base_url, stripped)
            encoded = urllib.parse.quote(absolute, safe="")
            out.append(f"{_PROXY_PATH}?path={encoded}{newline}")

        else:
            # Blank line
            out.append(line)

    return "".join(out)


@stream_proxy_bp.get("/api/stream/animeav1-proxy")
def animeav1_proxy():
    """Proxy Zilla manifest and segment requests with the required Referer header.

    Query params:
        path (required): URL-encoded full Zilla URL to fetch.

    Returns:
        200  — manifest (rewritten) or segment bytes
        400  — missing path parameter
        502  — Zilla returned a non-2xx status
    """
    encoded_path = request.args.get("path")
    if not encoded_path:
        return jsonify({"error": "Missing required query parameter: path"}), 400

    # Decode the path — Flask already URL-decodes query params, but handle
    # the case where it arrives double-encoded.
    target_url = encoded_path

    try:
        resp = requests.get(
            target_url,
            headers=_ZILLA_HEADERS,
            timeout=20,
            stream=True,
        )
    except requests.RequestException as exc:
        return jsonify({"error": f"Failed to reach upstream: {exc}"}), 502

    if not resp.ok:
        return (
            jsonify({"error": f"Upstream returned {resp.status_code}"}),
            502,
        )

    content_type = resp.headers.get("Content-Type", "application/octet-stream")

    if _is_m3u8(target_url, content_type):
        # Read full manifest and rewrite segment/variant lines
        manifest = resp.text
        rewritten = _rewrite_m3u8(manifest, target_url)
        return Response(
            rewritten,
            status=200,
            content_type="application/vnd.apple.mpegurl",
        )

    # Binary passthrough (segments, key files, etc.)
    def _generate():
        for chunk in resp.iter_content(chunk_size=65536):
            if chunk:
                yield chunk

    return Response(
        _generate(),
        status=200,
        content_type=content_type,
        direct_passthrough=True,
    )
