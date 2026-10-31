"""Photo AI through Ollama: settings, identifying a piece and its holder, a grade range, and pieces you already have.
Ollama is faked in its documented format (https://docs.ollama.com/api)."""

from __future__ import annotations

import base64
import json

import httpx
import pytest

from .test_photos import make_item, upload

IDENT = {
    "kind": "coin", "country": "United States", "denomination": "Quarter Dollar", "year": 1956, "mint_mark": "D",
    "series": "Washington Quarter", "metal": "silver", "weight_text": "", "title": "1956 D Washington Quarter",
    "holder": {"in_holder": False, "service": "", "grade": "", "cert_number": "", "pcgs_number": "", "label_text": ""},
    "confidence": "high", "notes": "",
}
SLAB = {
    **IDENT, "year": 2015, "mint_mark": "S", "series": "America the Beautiful Quarter", "title": "2015 S Bombay Hook Quarter Silver Proof",
    "holder": {"in_holder": True, "service": "PCGS", "grade": "PR70 DCAM", "cert_number": "3257-3628", "pcgs_number": "382795",
               "label_text": "2015-S 25C Bombay Hook NP, Silver PR70DCAM PCGS 32573628"},
}
GRADE = {"low": "VF 30", "high": "vf20", "summary": "Moderate wear on the high points.", "wear": "Hair and eagle breast worn.",
         "surfaces": "Even grey toning.", "problems": [], "photo_advice": ""}


class FakeOllama:
    def __init__(self):
        self.answer: dict | str = IDENT
        self.calls: list[tuple[str, dict | None]] = []
        self.down = False
        self.models = [
            {"name": "gemma4:26b", "model": "gemma4:26b", "size": 17_000_000_000, "details": {"parameter_size": "26B", "quantization_level": "Q4_K_M"}},
            {"name": "llama3:8b", "model": "llama3:8b", "size": 4_700_000_000, "details": {"parameter_size": "8.0B", "quantization_level": "Q4_0"}},
            {"name": "gemma4:cloud", "model": "gemma4:cloud", "remote_host": "https://ollama.com", "details": {}},
        ]

    def handler(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            raise httpx.ConnectError("refused", request=request)
        body = json.loads(request.content) if request.content else None
        self.calls.append((request.url.path, body))
        p = request.url.path
        if p == "/api/version":
            return httpx.Response(200, json={"version": "0.13.0"})
        if p == "/api/tags":
            return httpx.Response(200, json={"models": self.models})
        if p == "/api/show":
            caps = ["completion", "vision"] if body["model"].startswith("gemma") else ["completion"]
            return httpx.Response(200, json={"capabilities": caps, "details": {}})
        if p == "/api/chat":
            if body["model"] != "gemma4:26b":
                return httpx.Response(404, json={"error": f"model '{body['model']}' not found"})
            content = self.answer if isinstance(self.answer, str) else json.dumps(self.answer)
            return httpx.Response(200, json={
                "model": body["model"], "message": {"role": "assistant", "content": content}, "done": True,
                "total_duration": 4_200_000_000, "load_duration": 1_000_000_000,
            })
        return httpx.Response(404)

    def client(self, read_seconds: float) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.handler))


@pytest.fixture
def fake(monkeypatch):
    f = FakeOllama()
    import app.providers.ollama as o

    monkeypatch.setattr(o, "client", f.client)
    return f


def jpg(images, seed):
    return images["jpeg"](images["coin"](seed=seed))


def setup_ai(api):
    r = api.put("/api/v1/ai/settings", json={"url": "http://192.168.1.80:11434/", "model": "gemma4:26b"})
    assert r.status_code == 200, r.text
    return r.json()


def item_with_photos(api, images, title="Quarter", seeds=(41, 42)):
    item = make_item(api, title)
    files = [(f"{i}.jpg", jpg(images, s), "image/jpeg") for i, s in enumerate(seeds)]
    photos = upload(api, item["id"], files, roles=["obverse", "reverse"][: len(seeds)]).json()
    return item, photos


def test_settings_check_and_save(api, fake, make_user, app):
    assert api.get("/api/v1/ai").json() == {"ready": False, "model": None}
    r = api.post("/api/v1/ai/check", json={"url": "http://192.168.1.80:11434"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["version"] == "0.13.0"
    # cloud models are left out: photos would leave the network
    assert [(m["name"], m["vision"]) for m in d["models"]] == [("gemma4:26b", True), ("llama3:8b", False)]

    assert api.put("/api/v1/ai/settings", json={"url": "ftp://x", "model": "m"}).status_code == 422
    assert api.put("/api/v1/ai/settings", json={"url": "http://x:11434/api", "model": "m"}).status_code == 422
    assert api.put("/api/v1/ai/settings", json={"url": "http://x:11434", "model": ""}).status_code == 422
    s = setup_ai(api)
    assert s == {"ready": True, "model": "gemma4:26b", "url": "http://192.168.1.80:11434"}
    assert api.get("/api/v1/ai").json() == {"ready": True, "model": "gemma4:26b"}

    fake.down = True
    r = api.post("/api/v1/ai/check", json={"url": "http://192.168.1.80:11434"})
    assert r.status_code == 502 and "Couldn't reach" in r.json()["detail"]

    # turning it off
    assert api.put("/api/v1/ai/settings", json={"url": "", "model": "gemma4:26b"}).json()["ready"] is False

    # only an admin can change it
    from fastapi.testclient import TestClient

    from tests.conftest import Api

    with TestClient(app) as c:
        make_user("viewer", admin=False)
        other = Api(c)
        other.login("viewer")
        assert other.get("/api/v1/ai/settings").status_code == 403
        assert other.get("/api/v1/ai").status_code == 200


def test_identify_fills_the_form_and_sends_the_photos(api, fake, images):
    item, photos = item_with_photos(api, images)
    refs = [{"sha256": p["sha256"], "role": p["role"]} for p in photos]
    assert api.post("/api/v1/ai/identify", json={"photos": refs}).status_code == 503  # not set up
    setup_ai(api)

    r = api.post("/api/v1/ai/identify", json={"photos": refs, "item_id": item["id"]})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["model"] == "gemma4:26b" and d["seconds"] == 4.2 and d["confidence"] == "high"
    form = d["described"]
    assert form["item_type"] == "coin" and form["title"] == "1956 D Washington Quarter"
    assert form["details"]["country"] == "United States" and form["details"]["year"] == 1956
    assert form["details"]["mint_mark"] == "D" and form["details"]["series"] == "Washington"  # the title reader's own name for the design
    assert form["compositions"] and form["compositions"][0]["metal"] == "Ag"  # 90% silver quarter
    assert d["holder"] is None and d["same_photos"] == [] and d["same_coin"] == []

    path, body = fake.calls[-1]
    assert path == "/api/chat" and body["stream"] is False and body["format"]["type"] == "object"
    assert body["options"]["temperature"] == 0
    msg = body["messages"][1]
    assert len(msg["images"]) == 2 and "Photo 1 is the obverse" in msg["content"] and "Photo 2 is the reverse" in msg["content"]
    sent = base64.b64decode(msg["images"][0])
    assert sent[:3] == b"\xff\xd8\xff"  # a JPEG
    from PIL import Image
    import io

    assert max(Image.open(io.BytesIO(sent)).size) <= 1536


def test_identify_reads_a_holder_and_finds_what_you_have(api, fake, images):
    setup_ai(api)
    # one you already have: same year, design and mint mark
    have = api.post("/api/v1/items", json={
        "item_type": "coin", "title": "1956-D Quarter", "details": {"country": "United States", "year": 1956, "mint_mark": "D", "denomination": "25c"},
    }).json()
    other_mint = api.post("/api/v1/items", json={
        "item_type": "coin", "title": "1956 Quarter", "details": {"country": "United States", "year": 1956, "denomination": "25c"},
    }).json()
    item, photos = item_with_photos(api, images, seeds=(51, 52))
    refs = [{"sha256": p["sha256"], "role": p["role"]} for p in photos]

    d = api.post("/api/v1/ai/identify", json={"photos": refs}).json()
    assert [m["id"] for m in d["same_coin"]] == [have["id"]]
    assert d["same_coin"][0]["why"].startswith("1956 D")
    # the photos are already on `item`
    assert [(m["id"], m["why"]) for m in d["same_photos"]] == [(item["id"], "exact")]
    # ...but not when asking about that item itself
    d = api.post("/api/v1/ai/identify", json={"photos": refs, "item_id": item["id"]}).json()
    assert d["same_photos"] == []
    assert other_mint["id"] not in [m["id"] for m in d["same_coin"]]

    fake.answer = SLAB
    d = api.post("/api/v1/ai/identify", json={"photos": refs}).json()
    assert d["holder"]["service"] == "PCGS" and d["holder"]["cert_number"] == "3257-3628" and d["holder"]["pcgs_number"] == "382795"
    c = d["described"]["condition"]
    assert c["grading"] == "slabbed" and c["grading_service"] == "PCGS" and c["grade_text"].startswith("PR70") and c["sheldon_grade"] == 70
    assert c["cert_number"] == "3257-3628"
    assert d["described"]["details"]["pcgs_number"] == "382795"


def test_identify_from_library_photos_and_errors(api, fake, images):
    setup_ai(api)
    r = api.post("/api/v1/uploads", files=[("files", ("loose_obv.jpg", jpg(images, 61), "image/jpeg"))])
    assert r.status_code == 201
    sha = api.get("/api/v1/library").json()["files"][0]["sha256"]
    assert api.post("/api/v1/ai/identify", json={"photos": [{"sha256": sha, "role": "obverse"}]}).status_code == 200
    assert api.post("/api/v1/ai/identify", json={"photos": [{"sha256": "0" * 64}]}).status_code == 404

    fake.answer = "not json"
    r = api.post("/api/v1/ai/identify", json={"photos": [{"sha256": sha}]})
    assert r.status_code == 502 and "JSON" in r.json()["detail"]

    api.put("/api/v1/ai/settings", json={"url": "http://192.168.1.80:11434", "model": "missing:1b"})
    r = api.post("/api/v1/ai/identify", json={"photos": [{"sha256": sha}]})
    assert r.status_code == 502 and "ollama pull" in r.json()["detail"]

    fake.down = True
    r = api.post("/api/v1/ai/identify", json={"photos": [{"sha256": sha}]})
    assert r.status_code == 502 and "192.168.1.80:11434" in r.json()["detail"]


def test_grade_gives_a_tidy_range(api, fake, images):
    setup_ai(api)
    item, photos = item_with_photos(api, images, seeds=(71, 72))
    fake.answer = GRADE
    refs = [{"sha256": p["sha256"], "role": p["role"]} for p in photos]
    r = api.post("/api/v1/ai/grade", json={"photos": refs, "item_id": item["id"]})
    assert r.status_code == 200, r.text
    g = r.json()
    assert (g["low"], g["high"], g["low_number"], g["high_number"]) == ("VF20", "VF30", 20, 30)
    assert g["summary"] == "Moderate wear on the high points." and g["problems"] == [] and g["photo_advice"] is None
    assert "raw (not slabbed)" in fake.calls[-1][1]["messages"][1]["content"]

    fake.answer = {**GRADE, "low": "about uncirculated", "high": "nice"}
    assert api.post("/api/v1/ai/grade", json={"photos": refs}).status_code == 502


def test_parse_identified_is_careful():
    from app.services.ai import parse_identified

    i = parse_identified({**IDENT, "year": 0, "mint_mark": "p.", "country": "USA", "title": ""})
    assert i.year is None and i.mint_mark == "P" and i.country == "United States"
    assert i.title == "P Washington Quarter"
    i = parse_identified({**IDENT, "mint_mark": "Denver mint"})
    assert i.mint_mark is None
    i = parse_identified({**SLAB, "holder": {**SLAB["holder"], "service": "NGC", "pcgs_number": "123"}})
    assert i.holder.pcgs_number is None  # only PCGS labels carry PCGS numbers
