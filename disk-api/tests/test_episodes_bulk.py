from app.models import db


def _insert(series_id, ep):
    db.insert_file(
        filename=f"{series_id}-{ep}.mp4",
        stored_path=f"/x/{series_id}-{ep}.mp4",
        content_type="video/mp4",
        size_bytes=1,
        category="video",
        series_id=series_id,
        episode_number=ep,
    )


def test_bulk_lists_sorted_numbers(client):
    for ep in (3, 1, 2):
        _insert("s1", ep)
    _insert("s2", 9)
    r = client.get("/api/episodes/s1")
    assert r.status_code == 200
    assert r.json() == {"series_id": "s1", "episode_numbers": [1, 2, 3]}


def test_bulk_ignores_null_episode_and_unknown_series(client):
    db.insert_file(
        filename="a.mp4", stored_path="/x/a.mp4", content_type="video/mp4",
        size_bytes=1, category="video", series_id="s1", episode_number=None,
    )
    assert client.get("/api/episodes/s1").json()["episode_numbers"] == []
    r = client.get("/api/episodes/nope")
    assert r.status_code == 200 and r.json()["episode_numbers"] == []


def test_bulk_requires_api_key(client):
    r = client.get("/api/episodes/s1", headers={"X-API-Key": "bad"})
    assert r.status_code in (401, 403)


def test_single_episode_route_still_works(client):
    _insert("s1", 1)
    assert client.get("/api/episodes/s1/1").status_code == 200
    assert client.get("/api/episodes/s1/2").status_code == 404
