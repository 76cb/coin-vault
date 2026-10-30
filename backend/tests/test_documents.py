def test_pdf_receipt_linked_to_items(api, images):
    a = api.post("/api/v1/items", json={"item_type": "coin", "title": "A"}).json()
    b = api.post("/api/v1/items", json={"item_type": "coin", "title": "B"}).json()
    r = api.post(
        "/api/v1/documents",
        files={"file": ("invoice.pdf", images["pdf"], "application/pdf")},
        data={"kind": "invoice", "title": "Show invoice", "doc_date": "2025-04-12", "item_ids": [str(a["id"]), str(b["id"])]},
    )
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc["mime"] == "application/pdf" and sorted(doc["item_ids"]) == sorted([a["id"], b["id"]])
    assert api.get(f"/api/v1/items/{a['id']}").json()["documents"][0]["title"] == "Show invoice"
    f = api.get(doc["url"])
    assert f.status_code == 200 and f.content == images["pdf"] and f.headers["cache-control"] == "private, no-store"
    assert len(api.get(f"/api/v1/documents?item_id={b['id']}").json()) == 1

    linked = api.put(f"/api/v1/documents/{doc['id']}/links", json={"item_ids": [a["id"]]}).json()
    assert linked["item_ids"] == [a["id"]]
    assert api.patch(f"/api/v1/documents/{doc['id']}", json={"kind": "receipt"}).json()["kind"] == "receipt"
    assert api.delete(f"/api/v1/documents/{doc['id']}").status_code == 204
    assert api.get(doc["url"]).status_code == 404


def test_document_type_checked_by_content(api, images):
    r = api.post("/api/v1/documents", files={"file": ("receipt.pdf", b"MZ\x90\x00 not a pdf at all", "application/pdf")})
    assert r.status_code == 422
    r = api.post("/api/v1/documents", files={"file": ("cut.pdf", images["pdf"][:60], "application/pdf")})
    assert r.status_code == 422


def test_photo_of_receipt_strips_gps(api, images):
    import piexif

    raw = images["jpeg"](images["coin"](seed=50), gps=True)
    doc = api.post("/api/v1/documents", files={"file": ("receipt.jpg", raw, "image/jpeg")}, data={"kind": "receipt"}).json()
    assert doc["mime"] == "image/jpeg"
    assert not piexif.load(api.get(doc["url"]).content)["GPS"]


def test_documents_need_auth(client, api, images):
    doc = api.post("/api/v1/documents", files={"file": ("a.pdf", images["pdf"], "application/pdf")}).json()
    anon = client.__class__(client.app)
    assert anon.get(doc["url"]).status_code == 401
