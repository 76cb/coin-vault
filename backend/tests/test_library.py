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
