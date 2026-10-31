"""Non-destructive photo edits: the original is untouched; thumb and medium show the edits."""

import io

import numpy as np
import piexif
import pytest
from PIL import Image

from app.services import photo_edit, storage

from .test_photos import make_item, upload


def solid(w, h, rgb):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), rgb).save(buf, "PNG")
    return buf.getvalue()


def img(resp):
    assert resp.status_code == 200, resp.text
    return Image.open(io.BytesIO(resp.content))


def put(api, photo_id, edits):
    return api.put(f"/api/v1/photos/{photo_id}/edits", json={"edits": edits})


def test_crop_rotate_and_reset(api, images):
    item = make_item(api)
    raw = images["jpeg"](images["coin"](seed=11).resize((1200, 800)))
    photo = upload(api, item["id"], [("c.jpg", raw, "image/jpeg")]).json()[0]
    before = api.get(photo["urls"]["original"]).content

    r = put(api, photo["id"], {"rotate": 90, "crop": {"x": 0.25, "y": 0, "w": 0.5, "h": 0.5}})
    assert r.status_code == 200, r.text
    p = r.json()
    # rotated a quarter turn the frame is 800 x 1200; half of each side is kept
    assert (p["width"], p["height"]) == (400, 600) and p["edits"]["rotate"] == 90
    assert "?v=" in p["urls"]["medium"] and p["urls"]["medium"] != photo["urls"]["medium"]
    assert img(api.get(p["urls"]["medium"])).size == (400, 600)
    assert max(img(api.get(p["urls"]["thumb"])).size) == 400
    assert img(api.get(p["urls"]["unedited"])).size == (1200, 800)  # the editor's starting point
    assert img(api.get(p["urls"]["edited"])).size == (400, 600)
    assert api.get(p["urls"]["original"]).content == before  # never changed

    # the item list's cover thumbnail follows the edit
    listed = api.get("/api/v1/items", params={"q": item["title"]}).json()["items"][0]
    assert listed["cover_thumb_url"] == p["urls"]["thumb"]

    r = put(api, photo["id"], None)
    p = r.json()
    assert p["edits"] is None and (p["width"], p["height"]) == (1200, 800) and "?v=" not in p["urls"]["medium"]


def test_identity_edits_store_nothing(api, images):
    item = make_item(api)
    photo = upload(api, item["id"], [("c.jpg", images["jpeg"](images["coin"](seed=12)), "image/jpeg")]).json()[0]
    p = put(api, photo["id"], {"rotate": 0, "exposure": 0, "crop": {"x": 0, "y": 0, "w": 1, "h": 1}}).json()
    assert p["edits"] is None


def test_colour_math_matches_the_browser(api):
    item = make_item(api)
    photo = upload(api, item["id"], [("g.png", solid(64, 64, (100, 150, 200)), "image/png")]).json()[0]

    def pixel(edits):
        p = put(api, photo["id"], edits).json()
        a = np.asarray(img(api.get(p["urls"]["edited"])).convert("RGB"), dtype=float)
        return a[32, 32]

    # exposure +100 doubles each value (one stop)
    assert pixel({"exposure": 100}) == pytest.approx([200, 255, 255], abs=2)
    # contrast +100 doubles the distance from mid grey: (v-127.5)*2+127.5
    assert pixel({"contrast": 100}) == pytest.approx([72.5, 172.5, 255], abs=2)
    # saturation -100 is grey by Rec. 709 luminance
    grey = 0.2126 * 100 + 0.7152 * 150 + 0.0722 * 200
    assert pixel({"saturation": -100}) == pytest.approx([grey] * 3, abs=2)
    # warmth +100: red x1.15, blue x0.85
    assert pixel({"warmth": 100}) == pytest.approx([115, 150, 170], abs=2)


def test_straighten_fills_the_frame():
    assert photo_edit.straighten_zoom(100, 100, 0) == 1
    assert photo_edit.straighten_zoom(100, 100, 45) == pytest.approx(2 ** 0.5)
    original = Image.new("RGB", (300, 200), (255, 0, 0))
    out = photo_edit.render(original, {"straighten": 10}, None)
    k = photo_edit.straighten_zoom(300, 200, 10)
    assert out.size == (int(300 / k) - 2, int(200 / k) - 2)
    a = np.asarray(out)
    assert a[..., 0].min() > 200 and a[..., 2].max() < 60  # no empty (black) corners


def test_exif_orientation_is_applied_before_edits(api, images):
    item = make_item(api)
    base = images["coin"](seed=13).resize((1600, 1200))
    buf = io.BytesIO()
    base.save(buf, "JPEG", exif=piexif.dump({"0th": {piexif.ImageIFD.Orientation: 6}}))
    photo = upload(api, item["id"], [("r.jpg", buf.getvalue(), "image/jpeg")]).json()[0]
    p = put(api, photo["id"], {"crop": {"x": 0, "y": 0, "w": 1, "h": 0.5}}).json()
    assert (p["width"], p["height"]) == (1200, 800)  # portrait as shown, top half kept
    p = put(api, photo["id"], None).json()
    assert (p["width"], p["height"]) == (1200, 1600)


def test_bad_edits_are_refused(api, images):
    item = make_item(api)
    photo = upload(api, item["id"], [("c.jpg", images["jpeg"](images["coin"](seed=14)), "image/jpeg")]).json()[0]
    assert put(api, photo["id"], {"crop": {"x": 0.8, "y": 0, "w": 0.5, "h": 1}}).status_code == 422
    assert put(api, photo["id"], {"rotate": 45}).status_code == 422
    assert put(api, photo["id"], {"exposure": 500}).status_code == 422


def test_edited_copies_are_cleaned_up(api, images):
    item = make_item(api)
    photo = upload(api, item["id"], [("c.jpg", images["jpeg"](images["coin"](seed=15)), "image/jpeg")]).json()[0]
    p = put(api, photo["id"], {"exposure": 20}).json()
    from app.db import session_factory
    from app.models import Photo

    with session_factory()() as db:
        sha = db.get(Photo, photo["id"]).sha256
    first = photo_edit.edited_key(sha, "medium", photo_edit.edit_hash(p["edits"]))
    assert storage.exists(first)
    p = put(api, photo["id"], {"exposure": 40}).json()
    assert not storage.exists(first)  # replaced by the new edit's copies
    second = photo_edit.edited_key(sha, "medium", photo_edit.edit_hash(p["edits"]))
    assert storage.exists(second)
    assert api.delete(f"/api/v1/photos/{photo['id']}").status_code == 204
    assert not storage.exists(second)


def test_circle_cut_out(api, images):
    item = make_item(api)
    raw = images["jpeg"](images["coin"](seed=12).resize((1000, 1000)))
    photo = upload(api, item["id"], [("c.jpg", raw, "image/jpeg")]).json()[0]
    p = put(api, photo["id"], {"crop": {"x": 0.1, "y": 0.1, "w": 0.8, "h": 0.8}, "circle": True}).json()
    assert p["edits"] == {"crop": {"x": 0.1, "y": 0.1, "w": 0.8, "h": 0.8}, "circle": True}  # clear background is the default
    med = img(api.get(p["urls"]["medium"]))
    assert med.mode == "RGBA"
    a = np.asarray(med)
    assert a[0, 0, 3] == 0 and a[-1, -1, 3] == 0  # corners are see-through
    assert a[a.shape[0] // 2, a.shape[1] // 2, 3] == 255  # the coin isn't
    alpha = a[..., 3]
    assert ((alpha > 0) & (alpha < 255)).sum() > a.shape[0]  # a smooth edge, not a jagged one
    full = api.get(p["urls"]["edited"])
    assert full.headers["content-type"] == "image/png" and 'edited.png"' in full.headers["content-disposition"]
    assert Image.open(io.BytesIO(full.content)).size == (800, 800)

    p = put(api, photo["id"], {"crop": {"x": 0.1, "y": 0.1, "w": 0.8, "h": 0.8}, "circle": True, "background": "white"}).json()
    full = api.get(p["urls"]["edited"])
    assert full.headers["content-type"] == "image/jpeg"
    w = np.asarray(Image.open(io.BytesIO(full.content)).convert("RGB"))
    assert (w[2, 2] > 245).all()  # white outside the circle
    # a background without a circle is no edit at all
    assert put(api, photo["id"], {"background": "black"}).json()["edits"] is None


def test_find_the_coin(api, images):
    from PIL import ImageDraw

    item = make_item(api)
    # a dark coin of radius 300 centred at (900, 500) on a light, wide photo
    canvas = Image.new("RGB", (1600, 1000), (215, 205, 190))
    coin = images["coin"](seed=13).resize((750, 750)).point(lambda v: int(v * 0.45))
    mask = Image.new("L", (750, 750), 0)
    ImageDraw.Draw(mask).ellipse((75, 75, 675, 675), fill=255)
    canvas.paste(coin, (525, 125), mask)
    photo = upload(api, item["id"], [("wide.jpg", images["jpeg"](canvas), "image/jpeg")]).json()[0]

    r = api.post(f"/api/v1/photos/{photo['id']}/find-coin", json={})
    assert r.status_code == 200, r.text
    c = r.json()["crop"]
    assert abs(c["x"] * 1600 - 600) < 16 and abs(c["y"] * 1000 - 200) < 16  # the square around the rim
    assert abs(c["w"] * 1600 - 612) < 20 and abs(c["w"] * 1600 - c["h"] * 1000) < 2  # square, with a sliver of margin
    # turned a quarter: the frame is 1000 x 1600 and the coin is found in it
    t = api.post(f"/api/v1/photos/{photo['id']}/find-coin", json={"rotate": 90}).json()["crop"]
    assert abs(t["w"] * 1000 - 612) < 20 and abs((t["x"] + t["w"] / 2) * 1000 - 500) < 16
    assert put(api, photo["id"], {"crop": c, "circle": True}).status_code == 200

    bar = upload(api, item["id"], [("bar.png", solid(900, 400, (190, 190, 195)), "image/png")]).json()[0]
    r = api.post(f"/api/v1/photos/{bar['id']}/find-coin", json={})
    assert r.status_code == 404 and "Drag the circle" in r.json()["detail"]


def test_full_size_copy_is_made_once_and_cleaned_up(api, images):
    item = make_item(api)
    raw = images["jpeg"](images["coin"](seed=14).resize((900, 900)))
    photo = upload(api, item["id"], [("f.jpg", raw, "image/jpeg")]).json()[0]
    p = put(api, photo["id"], {"crop": {"x": 0.1, "y": 0.1, "w": 0.8, "h": 0.8}, "circle": True}).json()
    ehash = photo_edit.edit_hash(p["edits"])
    key = photo_edit.full_key(p["sha256"], ehash, "png")
    assert storage.exists(key)  # made right after saving, before anyone opens it
    first = api.get(p["urls"]["edited"])
    assert first.status_code == 200 and first.headers["content-type"] == "image/png"
    assert 'filename="f-edited.png"' in first.headers["content-disposition"]
    assert api.get(p["urls"]["edited"]).content == first.content
    # new edits: the old full-size copy goes, a new one comes
    p2 = put(api, photo["id"], {"crop": {"x": 0.1, "y": 0.1, "w": 0.8, "h": 0.8}, "circle": True, "background": "black"}).json()
    assert not storage.exists(key)
    key2 = photo_edit.full_key(p2["sha256"], photo_edit.edit_hash(p2["edits"]), "jpg")
    assert storage.exists(key2)
    assert api.delete(f"/api/v1/photos/{photo['id']}").status_code == 204
    assert not storage.exists(key2)
