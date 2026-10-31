"""Photo library: every uploaded image once, and putting one on another item without copying it."""

from .test_photos import make_item, upload


def jpg(images, seed):
    return images["jpeg"](images["coin"](seed=seed))


def test_library_lists_each_file_once_with_its_items(api, images):
    a = make_item(api, "A")
    b = make_item(api, "B")
    pa = upload(api, a["id"], [("a.jpg", jpg(images, 21), "image/jpeg")]).json()[0]
    upload(api, b["id"], [("b.jpg", jpg(images, 22), "image/jpeg")])
    # a bulk upload not filed yet
    r = api.post("/api/v1/uploads", files=[("files", ("loose.jpg", jpg(images, 23), "image/jpeg"))])
    assert r.status_code == 201, r.text

    lib = api.get("/api/v1/library").json()
    assert lib["total"] == 3
    by_name = {f["filename"]: f for f in lib["files"]}
    assert by_name["a.jpg"]["items"][0]["item_id"] == a["id"] and by_name["a.jpg"]["items"][0]["is_cover"]
    assert by_name["loose.jpg"]["items"] == [] and by_name["loose.jpg"]["waiting_upload"]
    assert [f["filename"] for f in api.get("/api/v1/library", params={"show": "not_on_items"}).json()["files"]] == ["loose.jpg"]
    assert api.get("/api/v1/library", params={"show": "on_items"}).json()["total"] == 2

    thumb = api.get(by_name["a.jpg"]["urls"]["thumb"])
    assert thumb.status_code == 200 and thumb.headers["content-type"] == "image/webp"

    # the same file on item B, as its cover: shared, not copied
    sha = by_name["a.jpg"]["sha256"]
    r = api.post(f"/api/v1/items/{b['id']}/photos/from-library", json={"sha256": sha, "role": "obverse", "make_cover": True})
    assert r.status_code == 201, r.text
    shared = r.json()
    full_b = api.get(f"/api/v1/items/{b['id']}").json()
    assert full_b["cover_photo_id"] == shared["id"] and len(full_b["photos"]) == 2
    assert {u["item_id"] for u in next(f for f in api.get("/api/v1/library").json()["files"] if f["sha256"] == sha)["items"]} == {a["id"], b["id"]}
    assert api.post(f"/api/v1/items/{b['id']}/photos/from-library", json={"sha256": sha}).status_code == 409

    # deleting it from A keeps the file for B
    assert api.delete(f"/api/v1/photos/{pa['id']}").status_code == 204
    assert api.get(shared["urls"]["original"]).status_code == 200

    # a loose bulk-upload file can go on an item too
    loose = by_name["loose.jpg"]["sha256"]
    assert api.post(f"/api/v1/items/{a['id']}/photos/from-library", json={"sha256": loose}).status_code == 201


def test_library_is_private(api, images, make_user, app):
    from fastapi.testclient import TestClient

    from tests.conftest import Api

    a = make_item(api, "Mine")
    upload(api, a["id"], [("m.jpg", jpg(images, 24), "image/jpeg")])
    sha = api.get("/api/v1/library").json()["files"][0]["sha256"]
    with TestClient(app) as c:
        make_user("someone-else")
        other = Api(c)
        other.login("someone-else")
        assert other.get("/api/v1/library").json()["total"] == 0
        assert other.get(f"/api/v1/media/library/{sha}/thumb").status_code == 404
        theirs = other.post("/api/v1/items", json={"item_type": "coin", "title": "Theirs"}).json()
        assert other.post(f"/api/v1/items/{theirs['id']}/photos/from-library", json={"sha256": sha}).status_code == 404
    assert api.get("/api/v1/media/library/not-a-hash/thumb").status_code == 404


def test_delete_photos_everywhere(api, images):
    from app.services import storage

    a = make_item(api, "Del A")
    b = make_item(api, "Del B")
    pa = upload(api, a["id"], [("x.jpg", jpg(images, 31), "image/jpeg")]).json()[0]
    upload(api, a["id"], [("y.jpg", jpg(images, 32), "image/jpeg")])
    lib = {f["filename"]: f for f in api.get("/api/v1/library").json()["files"]}
    x = lib["x.jpg"]["sha256"]
    api.post(f"/api/v1/items/{b['id']}/photos/from-library", json={"sha256": x, "make_cover": True})
    api.put(f"/api/v1/photos/{pa['id']}/edits", json={"edits": {"exposure": 30}})
    loose = api.post("/api/v1/uploads", files=[("files", ("z.jpg", jpg(images, 33), "image/jpeg"))]).json()
    z = next(f["sha256"] for f in api.get("/api/v1/library").json()["files"] if f["filename"] == "z.jpg")

    from app.db import session_factory
    from app.models import Photo
    with session_factory()() as db:
        key = db.get(Photo, pa["id"]).storage_key
    assert storage.exists(key)

    r = api.post("/api/v1/library/delete", json={"sha256s": [x, z]})
    assert r.status_code == 200, r.text
    assert r.json() == {"deleted": 2, "photos_removed": 2, "uploads_removed": 1}
    assert not storage.exists(key)  # nothing uses it any more
    names = {f["filename"] for f in api.get("/api/v1/library").json()["files"]}
    assert names == {"y.jpg"}
    # covers move on: A to its remaining photo, B to none
    full_a = api.get(f"/api/v1/items/{a['id']}").json()
    assert len(full_a["photos"]) == 1 and full_a["cover_photo_id"] == full_a["photos"][0]["id"]
    assert api.get(f"/api/v1/items/{b['id']}").json()["cover_photo_id"] is None
    # the emptied bulk-upload group is closed
    groups = api.get("/api/v1/uploads/groups").json()
    assert all(g["id"] != loose["groups"][0]["id"] for g in groups if g.get("status") == "pending")
    assert api.post("/api/v1/library/delete", json={"sha256s": [x]}).status_code == 404
