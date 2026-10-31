"""Pydantic request/response models for items, reference data and media."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models import (
    COST_STATUSES,
    DOC_KINDS,
    GRADINGS,
    ITEM_STATUSES,
    ITEM_TYPES,
    METALS,
    PHOTO_ROLES,
    VALUATION_RULES,
    WEIGHT_UNITS,
)

ItemType = Literal[ITEM_TYPES]  # type: ignore[valid-type]
ItemStatus = Literal[ITEM_STATUSES]  # type: ignore[valid-type]
CostStatus = Literal[COST_STATUSES]  # type: ignore[valid-type]
ValuationRule = Literal[VALUATION_RULES]  # type: ignore[valid-type]
Metal = Literal[METALS]  # type: ignore[valid-type]
PhotoRole = Literal[PHOTO_ROLES]  # type: ignore[valid-type]
DocKind = Literal[DOC_KINDS]  # type: ignore[valid-type]
WeightUnit = Literal[WEIGHT_UNITS]  # type: ignore[valid-type]
Grading = Literal[GRADINGS]  # type: ignore[valid-type]

Money = Decimal
NonNegMoney = Decimal


class _Base(BaseModel):
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)


# --- Type-specific details -------------------------------------------------------------


class CoinDetailsIn(_Base):
    country: str | None = Field(default=None, max_length=80)
    denomination: str | None = Field(default=None, max_length=80)
    year: int | None = Field(default=None, ge=-3000, le=2200)
    mint_mark: str | None = Field(default=None, max_length=10)
    series: str | None = Field(default=None, max_length=120)
    product_line: str | None = Field(default=None, max_length=120)
    mint: str | None = Field(default=None, max_length=120)
    diameter_mm: Decimal | None = Field(default=None, ge=0, le=1000)
    numista_id: int | None = Field(default=None, ge=1)
    pcgs_number: str | None = Field(default=None, max_length=20)
    redbook_number: str | None = Field(default=None, max_length=30)
    variety_notes: str | None = None


class BarDetailsIn(_Base):
    weight_value: Decimal | None = Field(default=None, gt=0)
    weight_unit: WeightUnit = "ozt"
    refiner: str | None = Field(default=None, max_length=120)
    serial_number: str | None = Field(default=None, max_length=60)
    has_assay_card: bool = False


class BanknoteDetailsIn(_Base):
    country: str | None = Field(default=None, max_length=80)
    denomination: str | None = Field(default=None, max_length=80)
    series: str | None = Field(default=None, max_length=80)
    serial_number: str | None = Field(default=None, max_length=60)
    pick_number: str | None = Field(default=None, max_length=30)


class LotDetailsIn(_Base):
    face_value: Decimal | None = Field(default=None, ge=0)
    face_currency: str = Field(default="USD", min_length=3, max_length=3)
    composition_id: int | None = None


class OtherDetailsIn(_Base):
    attributes: dict[str, Any] = Field(default_factory=dict)


DETAIL_MODELS: dict[str, type[_Base]] = {
    "coin": CoinDetailsIn,
    "bullion": CoinDetailsIn,
    "bar": BarDetailsIn,
    "banknote": BanknoteDetailsIn,
    "lot": LotDetailsIn,
    "other": OtherDetailsIn,
}


class ConditionIn(_Base):
    grading: Grading = "raw"
    sheldon_grade: int | None = Field(default=None, ge=1, le=70)
    grade_text: str | None = Field(default=None, max_length=60)
    grading_service: str | None = Field(default=None, max_length=30)
    cert_number: str | None = Field(default=None, max_length=40)
    designations: list[str] = Field(default_factory=list)
    details_reason: str | None = Field(default=None, max_length=120)

    @model_validator(mode="after")
    def _slab_fields(self) -> ConditionIn:
        if self.grading == "raw" and (self.grading_service or self.cert_number):
            raise ValueError("grading service and cert number apply only to slabbed items")
        return self


class MetalContentIn(_Base):
    metal: Metal
    gross_weight_g: Decimal | None = Field(default=None, gt=0)
    fineness: Decimal | None = Field(default=None, gt=0, le=1)
    pure_toz: Decimal | None = Field(default=None, ge=0, description="Set to override the computed value")
    composition_id: int | None = None


class MetalContentOut(_Base):
    id: int
    metal: str
    gross_weight_g: Decimal | None
    fineness: Decimal | None
    pure_toz: Decimal | None
    source: str
    composition_id: int | None


# --- Items -----------------------------------------------------------------------------


class _ItemFields(_Base):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    quantity: int | None = Field(default=None, ge=1)
    status: ItemStatus | None = None
    location_id: int | None = None
    acquired_date: dt.date | None = None
    purchase_price: Decimal | None = Field(default=None, ge=0)
    purchase_fees: Decimal | None = Field(default=None, ge=0)
    cost_basis_status: CostStatus | None = None
    purchase_source: str | None = Field(default=None, max_length=200)
    notes: str | None = None
    valuation_rule: ValuationRule | None = None
    sale_date: dt.date | None = None
    sale_price: Decimal | None = Field(default=None, ge=0)
    sale_fees: Decimal | None = Field(default=None, ge=0)
    sale_venue: str | None = Field(default=None, max_length=200)
    condition: ConditionIn | None = None
    details: dict[str, Any] | None = None
    metal_content: list[MetalContentIn] | None = None
    tags: list[str] | None = None

    @field_validator("tags")
    @classmethod
    def _clean_tags(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        out: list[str] = []
        for t in v:
            t = t.strip()
            if t and len(t) <= 60 and t.lower() not in {x.lower() for x in out}:
                out.append(t)
        return out


class ItemCreate(_ItemFields):
    item_type: ItemType
    title: str = Field(min_length=1, max_length=200)
    quantity: int = Field(default=1, ge=1)


class ItemUpdate(_ItemFields):
    """PATCH body. Fields left out are unchanged; send null to clear a field."""

    item_type: ItemType | None = None


class SaleIn(_Base):
    sale_date: dt.date
    sale_price: Decimal = Field(ge=0)
    sale_fees: Decimal | None = Field(default=None, ge=0)
    sale_venue: str | None = Field(default=None, max_length=200)


class PhotoOut(_Base):
    id: int
    item_id: int
    role: str
    sort_order: int
    width: int
    height: int
    bytes: int
    mime: str
    quality: dict[str, Any]
    original_filename: str | None
    created_at: dt.datetime
    urls: dict[str, str]


class DocumentSummary(_Base):
    id: int
    kind: str
    title: str
    doc_date: dt.date | None
    mime: str
    url: str


class ItemValuesOut(_Base):
    currency: str
    melt: Decimal | None
    melt_by_metal: dict[str, Decimal]
    melt_missing_spot: list[str]
    market: Decimal | None
    cost: Decimal | None
    current: Decimal | None
    gain: Decimal | None
    rule: str
    rule_applied: str
    pure_toz_total: dict[str, Decimal]


class ItemOut(_Base):
    id: int
    item_type: str
    title: str
    quantity: int
    status: str
    location_id: int | None
    location_path: str | None
    acquired_date: dt.date | None
    purchase_price: Decimal | None
    purchase_fees: Decimal | None
    cost_basis: Decimal | None
    cost_basis_status: str
    purchase_source: str | None
    notes: str | None
    valuation_rule: str
    sale_date: dt.date | None
    sale_price: Decimal | None
    sale_fees: Decimal | None
    sale_venue: str | None
    condition: ConditionIn | None
    details: dict[str, Any]
    metal_content: list[MetalContentOut]
    pure_toz_per_unit: dict[str, Decimal]
    values: ItemValuesOut
    tags: list[str]
    cover_photo_id: int | None
    cover_thumb_url: str | None
    photos: list[PhotoOut]
    documents: list[DocumentSummary]
    version: int
    created_at: dt.datetime
    updated_at: dt.datetime
    deleted_at: dt.datetime | None


class ItemListEntry(_Base):
    id: int
    item_type: str
    title: str
    quantity: int
    status: str
    location_path: str | None
    year: int | None
    country: str | None
    grade: str | None
    cost_basis: Decimal | None
    cost_basis_status: str
    tags: list[str]
    cover_thumb_url: str | None
    photo_count: int
    updated_at: dt.datetime
    melt: Decimal | None = None
    current: Decimal | None = None
    currency: str = "USD"
    deleted_at: dt.datetime | None


class ItemPage(BaseModel):
    items: list[ItemListEntry]
    total: int
    page: int
    page_size: int


class AuditEntry(_Base):
    id: int
    actor_type: str
    actor_id: int | None
    field: str
    old_value: str | None
    new_value: str | None
    at: dt.datetime


# --- Reference -------------------------------------------------------------------------


class LocationIn(_Base):
    name: str = Field(min_length=1, max_length=120)
    parent_id: int | None = None
    notes: str | None = None


class LocationOut(_Base):
    id: int
    name: str
    parent_id: int | None
    notes: str | None
    path: str
    item_count: int


class TagOut(_Base):
    id: int
    name: str
    item_count: int


class TagIn(_Base):
    name: str = Field(min_length=1, max_length=60)


# --- Photos, documents, uploads --------------------------------------------------------


class PhotoPatch(_Base):
    role: PhotoRole


class PhotoOrder(_Base):
    photo_ids: list[int] = Field(min_length=1)


class CoverIn(_Base):
    photo_id: int


class DocumentOut(_Base):
    id: int
    kind: str
    title: str
    doc_date: dt.date | None
    mime: str
    bytes: int
    original_filename: str | None
    created_at: dt.datetime
    item_ids: list[int]
    url: str


class DocumentPatch(_Base):
    kind: DocKind | None = None
    title: str | None = Field(default=None, min_length=1, max_length=200)
    doc_date: dt.date | None = None


class DocumentLinks(_Base):
    item_ids: list[int]


class UploadFileOut(_Base):
    id: int
    seq: int
    original_filename: str
    role: str
    width: int
    height: int
    bytes: int
    quality: dict[str, Any]
    duplicate_of_photo_id: int | None
    duplicate_of_item_id: int | None
    duplicate_kind: str | None
    urls: dict[str, str]


class UploadGroupOut(_Base):
    id: int
    batch_id: str
    pairing_rule: str
    label: str | None
    status: str
    resulting_item_id: int | None
    created_at: dt.datetime
    files: list[UploadFileOut]


class UploadResult(BaseModel):
    batch_id: str
    groups: list[UploadGroupOut]
    rejected: list[dict[str, str]]


class GroupPatch(_Base):
    label: str | None = Field(default=None, max_length=120)
    roles: dict[int, PhotoRole] | None = None


class GroupMerge(_Base):
    group_ids: list[int] = Field(min_length=2)


class GroupAttach(_Base):
    item_id: int


class GroupCreateItem(_Base):
    item: ItemCreate
