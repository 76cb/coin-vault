from app.services.pairing import parse_role, plan_groups


def test_parse_role_markers():
    assert parse_role("0042_obv.jpg") == ("0042", "obverse")
    assert parse_role("0042-REV.JPG") == ("0042", "reverse")
    assert parse_role("morgan 1881 front.png") == ("morgan 1881", "obverse")
    assert parse_role("0042_slab_back.jpg") == ("0042", "slab_back")
    assert parse_role("0042_edge.jpg") == ("0042", "edge")
    assert parse_role("photo.jpg") is None  # 'o' without a separator is not a marker
    assert parse_role("IMG_1234.jpg") is None


def test_plan_groups_patterns_then_order():
    names = ["0042_rev.jpg", "IMG_0002.jpg", "0042_obv.jpg", "IMG_0001.jpg", "0043_obv.jpg", "IMG_0010.jpg"]
    groups = plan_groups(names)
    by_label = {g.label: g for g in groups}
    g42 = by_label["0042"]
    assert g42.rule == "pattern"
    assert [(names[i], r) for i, r in g42.members] == [("0042_obv.jpg", "obverse"), ("0042_rev.jpg", "reverse")]
    assert by_label["0043"].rule == "single"
    pair = by_label["IMG_0001"]
    assert pair.rule == "order" and [names[i] for i, _ in pair.members] == ["IMG_0001.jpg", "IMG_0002.jpg"]
    assert [r for _, r in pair.members] == ["obverse", "reverse"]
    assert by_label["IMG_0010"].rule == "single"  # natural sort: 0010 after 0002, left over


def test_duplicate_roles_in_group_become_other():
    groups = plan_groups(["a_obv.jpg", "a-front.jpg"])
    assert sorted(r for _, r in groups[0].members) == ["obverse", "other"]


def _bulk(api, files):
    return api.post("/api/v1/uploads", files=[("files", f) for f in files])


def test_bulk_upload_pairs_and_rejects(api, images):
    f = lambda name, seed: (name, images["jpeg"](images["coin"](seed=seed)), "image/jpeg")  # noqa: E731
    r = _bulk(api, [f("0042_obv.jpg", 1), f("0042_rev.jpg", 2), f("IMG_1.jpg", 3), f("IMG_2.jpg", 4), ("notes.txt", b"hello", "text/plain")])
    assert r.status_code == 201, r.text
    body = r.json()
    assert len(body["groups"]) == 2
    assert body["rejected"] == [{"filename": "notes.txt", "reason": "Not a supported image (JPEG, PNG, WebP, HEIC or AVIF)"}]
    roles = [[x["role"] for x in g["files"]] for g in body["groups"]]
    assert roles == [["obverse", "reverse"], ["obverse", "reverse"]]
    assert api.get(body["groups"][0]["files"][0]["urls"]["thumb"]).status_code == 200
    pending = api.get("/api/v1/uploads/groups").json()
    assert len(pending) == 2


def test_create_item_from_group_and_attach(api, images):
    f = lambda name, seed: (name, images["jpeg"](images["coin"](seed=seed)), "image/jpeg")  # noqa: E731
    groups = _bulk(api, [f("7_obv.jpg", 5), f("7_rev.jpg", 6), f("8_obv.jpg", 7)]).json()["groups"]
    g7 = next(g for g in groups if g["label"] == "7")
    r = api.post(f"/api/v1/uploads/groups/{g7['id']}/create-item", json={"item": {"item_type": "coin", "title": "From upload"}})
    assert r.status_code == 201, r.text
    item = r.json()
    assert [p["role"] for p in item["photos"]] == ["obverse", "reverse"]
    assert item["cover_photo_id"] == item["photos"][0]["id"]
    # Same group cannot be used twice.
    assert api.post(f"/api/v1/uploads/groups/{g7['id']}/create-item", json={"item": {"item_type": "coin", "title": "x"}}).status_code == 409

    g8 = next(g for g in groups if g["label"] == "8")
    attached = api.post(f"/api/v1/uploads/groups/{g8['id']}/attach", json={"item_id": item["id"]}).json()
    assert len(attached["photos"]) == 3
    assert api.get("/api/v1/uploads/groups").json() == []
    done = api.get("/api/v1/uploads/groups?status=all").json()
    assert {g["status"] for g in done} == {"created_item", "attached"}


def test_split_merge_roles_discard(api, images):
    f = lambda name, seed: (name, images["jpeg"](images["coin"](seed=seed)), "image/jpeg")  # noqa: E731
    group = _bulk(api, [f("A1.jpg", 8), f("A2.jpg", 9)]).json()["groups"][0]
    parts = api.post(f"/api/v1/uploads/groups/{group['id']}/split").json()
    assert len(parts) == 2 and all(len(p["files"]) == 1 for p in parts)
    merged = api.post("/api/v1/uploads/groups/merge", json={"group_ids": [p["id"] for p in parts]}).json()
    assert len(merged["files"]) == 2
    fid = merged["files"][1]["id"]
    patched = api.patch(f"/api/v1/uploads/groups/{merged['id']}", json={"roles": {str(fid): "edge"}, "label": "Mystery coin"}).json()
    assert patched["files"][1]["role"] == "edge" and patched["label"] == "Mystery coin"
    assert api.post(f"/api/v1/uploads/groups/{merged['id']}/discard").json()["status"] == "discarded"
    assert api.get("/api/v1/uploads/groups").json() == []


def test_upload_flags_duplicate_of_existing_photo(api, images):
    raw = images["jpeg"](images["coin"](seed=40))
    item = api.post("/api/v1/items", json={"item_type": "coin", "title": "Have it"}).json()
    api.post(f"/api/v1/items/{item['id']}/photos", files=[("files", ("x.jpg", raw, "image/jpeg"))])
    group = _bulk(api, [("again.jpg", raw, "image/jpeg")]).json()["groups"][0]
    assert group["files"][0]["duplicate_kind"] == "exact"
    assert group["files"][0]["duplicate_of_item_id"] == item["id"]
