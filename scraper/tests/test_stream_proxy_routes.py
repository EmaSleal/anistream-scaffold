"""Unit tests for the AnimeAV1/Zilla manifest-rewrite proxy."""
import sys
import os
import urllib.parse
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from routes.stream_proxy_routes import _rewrite_m3u8

_BASE_URL = (
    "https://player.zilla-networks.com/segs/f7fb6ee0028474fcf48d821e414bc3df/"
    "f7fb6ee0028474fcf48d821e414bc3df.m3u8"
)
_PROXY_PATH = "/api/stream/animeav1-proxy"


def test_rewrite_m3u8_proxies_ext_x_map_uri():
    """#EXT-X-MAP init segment URI must be proxied, not left pointing at Zilla directly."""
    manifest = (
        "#EXTM3U\n"
        "#EXT-X-VERSION:7\n"
        '#EXT-X-MAP:URI="init.html"\n'
        "#EXTINF:6.0,\n"
        "seg0.ts\n"
    )

    rewritten = _rewrite_m3u8(manifest, _BASE_URL)

    assert 'URI="https://player.zilla-networks.com' not in rewritten
    expected_target = (
        "https://player.zilla-networks.com/segs/f7fb6ee0028474fcf48d821e414bc3df/init.html"
    )
    encoded = urllib.parse.quote(expected_target, safe="")
    assert f'#EXT-X-MAP:URI="{_PROXY_PATH}?path={encoded}"' in rewritten


def test_rewrite_m3u8_proxies_ext_x_key_uri():
    """Regression: #EXT-X-KEY URI rewriting must keep working alongside #EXT-X-MAP."""
    manifest = '#EXT-X-KEY:METHOD=AES-128,URI="key.bin"\nseg0.ts\n'

    rewritten = _rewrite_m3u8(manifest, _BASE_URL)

    assert 'URI="https://player.zilla-networks.com' not in rewritten
    assert f'#EXT-X-KEY:METHOD=AES-128,URI="{_PROXY_PATH}?path=' in rewritten


def test_rewrite_m3u8_proxies_segment_lines():
    manifest = "#EXTM3U\nseg0.ts\nseg1.ts\n"

    rewritten = _rewrite_m3u8(manifest, _BASE_URL)

    lines = [line for line in rewritten.splitlines() if line and not line.startswith("#")]
    assert all(line.startswith(_PROXY_PATH) for line in lines)


def test_rewrite_m3u8_passes_through_other_tags_unchanged():
    manifest = "#EXTM3U\n#EXT-X-VERSION:7\n#EXTINF:6.0,\nseg0.ts\n"

    rewritten = _rewrite_m3u8(manifest, _BASE_URL)

    assert "#EXT-X-VERSION:7" in rewritten
    assert "#EXTINF:6.0," in rewritten
