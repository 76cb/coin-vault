import io

import piexif
from PIL import Image

from app.services import storage


def make_item(api, title="Photo test"):
    return api.post("/api/v1/items", json={"item_type": "coin", "title": title}).json()


def upload(api, item_id, files, roles=None):
    data = {"roles": roles} if roles else None
    return api.post(f"/api/v1/items/{item_id}/photos", files=[("files", f) for f in files], data=data)


def test_upload_strips_gps_and_keeps_pixels(api, images):
    item = make_item(api)
    img = images["coin"](seed=3)
    raw = images["jpeg"](img, gps=True)
    assert piexif.load(raw)["GPS"]
    r = upload(api, item["id"], [("obv.jpg", raw, "image/jpeg")], roles=["obverse"])
    assert r.status_code == 201, r.text
    photo = r.json()[0]
    assert photo["role"] == "obverse" and photo["quality"]["gps_removed"] is True
    full = api.get(f"/api/v1/items/{item['id']}").json()
    assert full["cover_photo_id"] == photo["id"]

    original = api.get(photo["urls"]["original"])
    assert original.status_code == 200 and original.headers["content-type"] == "image/jpeg"
    assert not piexif.load(original.content)["GPS"]
    assert piexif.load(original.content)["0th"][piexif.ImageIFD.Make] == b"TestCam"  # other EXIF kept
    # Lossless: decoded pixels are identical to what was uploaded.
    assert Image.open(io.BytesIO(original.content)).tobytes() == Image.open(io.BytesIO(raw)).tobytes()

    thumb = api.get(photo["urls"]["thumb"])
    assert thumb.headers["content-type"] == "image/webp"
    assert max(Image.open(io.BytesIO(thumb.content)).size) <= 400


def test_auto_rotate_uses_exif_orientation(api, images):
    item = make_item(api)
    img = images["coin"](seed=4).resize((1600, 1200))
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=piexif.dump({"0th": {piexif.ImageIFD.Orientation: 6}}))  # rotated 90°
    photo = upload(api, item["id"], [("r.jpg", buf.getvalue(), "image/jpeg")]).json()[0]
    assert (photo["width"], photo["height"]) == (1200, 1600)
    med = Image.open(io.BytesIO(api.get(photo["urls"]["medium"]).content))
    assert med.size[1] > med.size[0]


def test_quality_check_flags_blur_glare_and_low_resolution(api, images):
    item = make_item(api)
    sharp = images["jpeg"](images["coin"](seed=5))
    blurry = images["jpeg"](images["coin"](seed=6, blur=6))
    glare = images["jpeg"](images["coin"](seed=7, glare=True))
    small = images["jpeg"](images["coin"](seed=8, size=600))
    res = upload(api, item["id"], [(n, b, "image/jpeg") for n, b in [("a.jpg", sharp), ("b.jpg", blurry), ("c.jpg", glare), ("d.jpg", small)]]).json()
    issues = [{i["check"] for i in p["quality"]["issues"]} for p in res]
    assert res[0]["quality"]["verdict"] == "pass", res[0]["quality"]
    assert "blur" in issues[1]
    assert "glare" in issues[2]
    assert "resolution" in issues[3]


def test_rejects_non_images_and_oversize(api, images, monkeypatch):
    item = make_item(api)
    r = upload(api, item["id"], [("fake.jpg", b"<html>not an image</html>", "image/jpeg")])
    assert r.status_code == 422 and "supported image" in r.json()["detail"]
    r = upload(api, item["id"], [("doc.jpg", images["pdf"], "image/jpeg")])
    assert r.status_code == 422
    truncated = images["jpeg"](images["coin"](seed=9))[:2000]
    assert upload(api, item["id"], [("cut.jpg", truncated, "image/jpeg")]).status_code == 422

    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "max_photo_mb", 0)
    r = upload(api, item["id"], [("big.jpg", images["jpeg"](images["coin"](seed=10)), "image/jpeg")])
    assert r.status_code == 413


def test_png_with_gps_is_cleaned(api, images):
    item = make_item(api)
    img = images["coin"](seed=11)
    exif = Image.Exif()
    exif[0x8825] = {2: (38.0, 41.0, 0.0)}
    buf = io.BytesIO()
    img.save(buf, "PNG", exif=exif.tobytes())
    photo = upload(api, item["id"], [("p.png", buf.getvalue(), "image/png")]).json()[0]
    assert photo["quality"]["gps_removed"] is True
    stored = Image.open(io.BytesIO(api.get(photo["urls"]["original"]).content))
    assert not stored.getexif().get_ifd(0x8825)


def test_duplicate_detection(api, images):
    a = make_item(api, "A")
    b = make_item(api, "B")
    img = images["coin"](seed=12)
    raw = images["jpeg"](img)
    first = upload(api, a["id"], [("x.jpg", raw, "image/jpeg")]).json()[0]
    assert first["duplicate_kind"] is None
    same = upload(api, b["id"], [("x.jpg", raw, "image/jpeg")]).json()[0]
    assert same["duplicate_kind"] == "exact" and same["duplicate_of_item_id"] == a["id"]
    similar_bytes = images["jpeg"](img.resize((1400, 1400)), quality=70)
    similar = upload(api, b["id"], [("y.jpg", similar_bytes, "image/jpeg")]).json()[0]
    assert similar["duplicate_kind"] == "similar"
    other = upload(api, b["id"], [("z.jpg", images["jpeg"](images["coin"](seed=99)), "image/jpeg")]).json()[0]
    assert other["duplicate_kind"] is None


def test_roles_order_cover_and_delete(api, images):
    item = make_item(api)
    files = [(f"{i}.jpg", images["jpeg"](images["coin"](seed=20 + i)), "image/jpeg") for i in range(3)]
    photos = upload(api, item["id"], files, roles=["obverse", "reverse", "edge"]).json()
    ids = [p["id"] for p in photos]
    assert api.patch(f"/api/v1/photos/{ids[2]}", json={"role": "slab_front"}).json()["role"] == "slab_front"
    reordered = api.put(f"/api/v1/items/{item['id']}/photos/order", json={"photo_ids": [ids[2], ids[0], ids[1]]}).json()
    assert [p["id"] for p in reordered] == [ids[2], ids[0], ids[1]]
    assert api.put(f"/api/v1/items/{item['id']}/photos/order", json={"photo_ids": [ids[0]]}).status_code == 422
    assert api.put(f"/api/v1/items/{item['id']}/cover", json={"photo_id": ids[1]}).status_code == 204
    assert api.get(f"/api/v1/items/{item['id']}").json()["cover_photo_id"] == ids[1]

    key_path = storage.path_for(storage.derived_key(_sha(api, ids[1]), "thumb"))
    assert key_path.exists()
    assert api.delete(f"/api/v1/photos/{ids[1]}").status_code == 204
    after = api.get(f"/api/v1/items/{item['id']}").json()
    assert after["cover_photo_id"] == ids[0]  # falls back to the obverse
    assert not key_path.exists()  # unreferenced files are removed


def _sha(api, photo_id):
    from app.db import session_factory
    from app.models import Photo

    with session_factory()() as db:
        return db.get(Photo, photo_id).sha256


def test_media_requires_owner(app, api, images, make_user):
    from fastapi.testclient import TestClient

    from tests.conftest import Api

    item = make_item(api)
    photo = upload(api, item["id"], [("a.jpg", images["jpeg"](images["coin"](seed=30)), "image/jpeg")]).json()[0]
    with TestClient(app) as anon:
        assert anon.get(photo["urls"]["thumb"]).status_code == 401
        make_user("second", admin=False)
        other = Api(anon)
        other.login("second")
        assert other.get(photo["urls"]["thumb"]).status_code == 404


def test_x_accel_redirect_mode(api, images, monkeypatch):
    from app.config import get_settings

    item = make_item(api)
    photo = upload(api, item["id"], [("a.jpg", images["jpeg"](images["coin"](seed=31)), "image/jpeg")]).json()[0]
    monkeypatch.setattr(get_settings(), "use_x_accel", True)
    r = api.get(photo["urls"]["thumb"])
    assert r.status_code == 200 and r.headers["x-accel-redirect"].startswith("/protected-media/derived/")
    assert r.content == b""


def test_media_files_are_group_readable(app):
    """nginx (in the coinvault group) serves media via X-Accel, so files must be g+r, not mkstemp's 0600."""
    import stat

    from app.services import storage

    storage.write_bytes("originals/aa/bb/perm-test.jpg", b"x")
    mode = stat.S_IMODE(storage.path_for("originals/aa/bb/perm-test.jpg").stat().st_mode)
    assert mode & stat.S_IRGRP and not mode & stat.S_IROTH
