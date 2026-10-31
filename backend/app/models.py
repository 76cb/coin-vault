"""SQLAlchemy models for Milestone 1.

Conventions: money NUMERIC(14,4); weights NUMERIC(14,6); timestamps are timezone-aware UTC;
every user-owned row carries owner_id so more users can be added without a migration of meaning.
Enumerations are stored as short strings with CHECK constraints (portable across Postgres and SQLite).
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

MONEY = Numeric(14, 4)
WEIGHT = Numeric(14, 6)
FINENESS = Numeric(6, 5)

ITEM_TYPES = ("coin", "bullion", "bar", "banknote", "lot", "other")
ITEM_STATUSES = ("owned", "for_sale", "sold")
COST_STATUSES = ("known", "estimated", "unknown")
VALUATION_RULES = ("max", "melt", "market", "cost")
METALS = ("Au", "Ag", "Pt", "Pd")
PHOTO_ROLES = ("obverse", "reverse", "edge", "slab_front", "slab_back", "other")
DOC_KINDS = ("receipt", "invoice", "certificate", "assay_card", "other")
WEIGHT_UNITS = ("g", "ozt", "kg", "tola")
GRADINGS = ("raw", "slabbed")
GROUP_STATUSES = ("pending", "attached", "created_item", "discarded")


def _in(col: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{col} IN ({quoted})"


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


TS = DateTime(timezone=True)


# --- Identity ---------------------------------------------------------------------------


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    base_currency: Mapped[str] = mapped_column(String(3), default="USD")
    created_at: Mapped[dt.datetime] = mapped_column(TS, default=utcnow)
    last_login_at: Mapped[dt.datetime | None] = mapped_column(TS)


class UserSession(Base):
    __tablename__ = "sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[dt.datetime] = mapped_column(TS, default=utcnow)
    last_seen_at: Mapped[dt.datetime] = mapped_column(TS, default=utcnow)
    expires_at: Mapped[dt.datetime] = mapped_column(TS)
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(255))

    user: Mapped[User] = relationship()


class ApiToken(Base):
    __tablename__ = "api_tokens"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    prefix: Mapped[str] = mapped_column(String(16), unique=True)
    token_hash: Mapped[str] = mapped_column(String(64))
    scopes: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[dt.datetime] = mapped_column(TS, default=utcnow)
    last_used_at: Mapped[dt.datetime | None] = mapped_column(TS)
    expires_at: Mapped[dt.datetime | None] = mapped_column(TS)
    revoked_at: Mapped[dt.datetime | None] = mapped_column(TS)

    user: Mapped[User] = relationship()


# --- Reference --------------------------------------------------------------------------


class Location(Base):
    __tablename__ = "locations"
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(Text)


item_tags = Table(
    "item_tags",
    Base.metadata,
    Column("item_id", ForeignKey("items.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


class Tag(Base):
    __tablename__ = "tags"
    __table_args__ = (UniqueConstraint("owner_id", "name", name="uq_tags_owner_name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(60))


class Composition(Base):
    """Reference ASW/AGW table. Seeded in Milestone 2; users may add their own rows."""

    __tablename__ = "compositions"
    __table_args__ = (CheckConstraint(_in("metal", METALS), name="metal"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(120), unique=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    label: Mapped[str] = mapped_column(String(200))
    country: Mapped[str | None] = mapped_column(String(80))
    denomination: Mapped[str | None] = mapped_column(String(80))
    year_from: Mapped[int | None] = mapped_column(Integer)
    year_to: Mapped[int | None] = mapped_column(Integer)
    mint_marks: Mapped[list[str] | None] = mapped_column(JSON)
    metal: Mapped[str] = mapped_column(String(2))
    fineness: Mapped[Decimal | None] = mapped_column(FINENESS)
    gross_weight_g: Mapped[Decimal | None] = mapped_column(WEIGHT)
    pure_toz: Mapped[Decimal] = mapped_column(WEIGHT)
    per_face_unit: Mapped[bool] = mapped_column(Boolean, default=False)
    citation: Mapped[str | None] = mapped_column(Text)


# --- Items ------------------------------------------------------------------------------


class Item(Base):
    __tablename__ = "items"
    __table_args__ = (
        CheckConstraint(_in("item_type", ITEM_TYPES), name="item_type"),
        CheckConstraint(_in("status", ITEM_STATUSES), name="status"),
        CheckConstraint(_in("cost_basis_status", COST_STATUSES), name="cost_basis_status"),
        CheckConstraint(_in("valuation_rule", VALUATION_RULES), name="valuation_rule"),
        CheckConstraint("quantity >= 1", name="quantity_positive"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    item_type: Mapped[str] = mapped_column(String(16), index=True)
    title: Mapped[str] = mapped_column(String(200))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(16), default="owned", index=True)
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id", ondelete="SET NULL"))
    acquired_date: Mapped[dt.date | None] = mapped_column(Date)
    purchase_price: Mapped[Decimal | None] = mapped_column(MONEY)
    purchase_fees: Mapped[Decimal | None] = mapped_column(MONEY)
    cost_basis_status: Mapped[str] = mapped_column(String(16), default="unknown")
    purchase_source: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)
    cover_photo_id: Mapped[int | None] = mapped_column(
        ForeignKey("photos.id", ondelete="SET NULL", use_alter=True, name="fk_items_cover_photo_id_photos")
    )
    valuation_rule: Mapped[str] = mapped_column(String(16), default="max")
    sale_date: Mapped[dt.date | None] = mapped_column(Date)
    sale_price: Mapped[Decimal | None] = mapped_column(MONEY)
    sale_fees: Mapped[Decimal | None] = mapped_column(MONEY)
    sale_venue: Mapped[str | None] = mapped_column(String(200))
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[dt.datetime] = mapped_column(TS, default=utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(TS, default=utcnow, onupdate=utcnow)
    deleted_at: Mapped[dt.datetime | None] = mapped_column(TS, index=True)

    location: Mapped[Location | None] = relationship()
    tags: Mapped[list[Tag]] = relationship(secondary=item_tags, order_by="Tag.name")
    condition: Mapped[ItemCondition | None] = relationship(cascade="all, delete-orphan", uselist=False)
    coin: Mapped[CoinDetails | None] = relationship(cascade="all, delete-orphan", uselist=False)
    bar: Mapped[BarDetails | None] = relationship(cascade="all, delete-orphan", uselist=False)
    banknote: Mapped[BanknoteDetails | None] = relationship(cascade="all, delete-orphan", uselist=False)
    lot: Mapped[LotDetails | None] = relationship(cascade="all, delete-orphan", uselist=False)
    other: Mapped[OtherDetails | None] = relationship(cascade="all, delete-orphan", uselist=False)
    metal_content: Mapped[list[ItemMetalContent]] = relationship(
        cascade="all, delete-orphan", order_by="ItemMetalContent.id"
    )
    valuations: Mapped[list[Valuation]] = relationship(
        cascade="all, delete-orphan", order_by="(Valuation.as_of.desc(), Valuation.id.desc())", back_populates="item"
    )
    photos: Mapped[list[Photo]] = relationship(
        cascade="all, delete-orphan", order_by="(Photo.sort_order, Photo.id)", foreign_keys="Photo.item_id"
    )


class ItemCondition(Base):
    __tablename__ = "item_condition"
    __table_args__ = (CheckConstraint(_in("grading", GRADINGS), name="grading"),)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), primary_key=True)
    grading: Mapped[str] = mapped_column(String(8), default="raw")
    sheldon_grade: Mapped[int | None] = mapped_column(Integer)
    grade_text: Mapped[str | None] = mapped_column(String(60))
    grading_service: Mapped[str | None] = mapped_column(String(30))
    cert_number: Mapped[str | None] = mapped_column(String(40))
    designations: Mapped[list[str]] = mapped_column(JSON, default=list)
    details_reason: Mapped[str | None] = mapped_column(String(120))


class CoinDetails(Base):
    """Used by both 'coin' and 'bullion' items."""

    __tablename__ = "coin_details"
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), primary_key=True)
    country: Mapped[str | None] = mapped_column(String(80))
    denomination: Mapped[str | None] = mapped_column(String(80))
    year: Mapped[int | None] = mapped_column(Integer)
    mint_mark: Mapped[str | None] = mapped_column(String(10))
    series: Mapped[str | None] = mapped_column(String(120))
    product_line: Mapped[str | None] = mapped_column(String(120))
    mint: Mapped[str | None] = mapped_column(String(120))
    diameter_mm: Mapped[Decimal | None] = mapped_column(Numeric(7, 2))
    numista_id: Mapped[int | None] = mapped_column(Integer)
    pcgs_number: Mapped[str | None] = mapped_column(String(20))
    redbook_number: Mapped[str | None] = mapped_column(String(30))
    variety_notes: Mapped[str | None] = mapped_column(Text)


class BarDetails(Base):
    __tablename__ = "bar_details"
    __table_args__ = (CheckConstraint(_in("weight_unit", WEIGHT_UNITS), name="weight_unit"),)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), primary_key=True)
    weight_value: Mapped[Decimal | None] = mapped_column(WEIGHT)
    weight_unit: Mapped[str] = mapped_column(String(4), default="ozt")
    refiner: Mapped[str | None] = mapped_column(String(120))
    serial_number: Mapped[str | None] = mapped_column(String(60))
    has_assay_card: Mapped[bool] = mapped_column(Boolean, default=False)


class BanknoteDetails(Base):
    __tablename__ = "banknote_details"
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), primary_key=True)
    country: Mapped[str | None] = mapped_column(String(80))
    denomination: Mapped[str | None] = mapped_column(String(80))
    series: Mapped[str | None] = mapped_column(String(80))
    serial_number: Mapped[str | None] = mapped_column(String(60))
    pick_number: Mapped[str | None] = mapped_column(String(30))


class LotDetails(Base):
    __tablename__ = "lot_details"
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), primary_key=True)
    face_value: Mapped[Decimal | None] = mapped_column(MONEY)
    face_currency: Mapped[str] = mapped_column(String(3), default="USD")
    composition_id: Mapped[int | None] = mapped_column(ForeignKey("compositions.id", ondelete="SET NULL"))


class OtherDetails(Base):
    __tablename__ = "other_details"
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), primary_key=True)
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)


class ItemMetalContent(Base):
    __tablename__ = "item_metal_content"
    __table_args__ = (
        CheckConstraint(_in("metal", METALS), name="metal"),
        CheckConstraint(_in("source", ("reference", "computed", "override")), name="source"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), index=True)
    metal: Mapped[str] = mapped_column(String(2))
    gross_weight_g: Mapped[Decimal | None] = mapped_column(WEIGHT)
    fineness: Mapped[Decimal | None] = mapped_column(FINENESS)
    pure_toz: Mapped[Decimal | None] = mapped_column(WEIGHT)
    source: Mapped[str] = mapped_column(String(10), default="computed")
    composition_id: Mapped[int | None] = mapped_column(ForeignKey("compositions.id", ondelete="SET NULL"))


# --- Media ------------------------------------------------------------------------------


class Photo(Base):
    __tablename__ = "photos"
    __table_args__ = (CheckConstraint(_in("role", PHOTO_ROLES), name="role"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(12), default="other")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    storage_key: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    phash: Mapped[str | None] = mapped_column(String(16))
    mime: Mapped[str] = mapped_column(String(40))
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    bytes: Mapped[int] = mapped_column(Integer)
    quality: Mapped[dict] = mapped_column(JSON, default=dict)
    original_filename: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[dt.datetime] = mapped_column(TS, default=utcnow)


document_links = Table(
    "document_links",
    Base.metadata,
    Column("document_id", ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True),
    Column("item_id", ForeignKey("items.id", ondelete="CASCADE"), primary_key=True),
)


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (CheckConstraint(_in("kind", DOC_KINDS), name="kind"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(12), default="other")
    title: Mapped[str] = mapped_column(String(200))
    doc_date: Mapped[dt.date | None] = mapped_column(Date)
    storage_key: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64))
    mime: Mapped[str] = mapped_column(String(40))
    bytes: Mapped[int] = mapped_column(Integer)
    original_filename: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[dt.datetime] = mapped_column(TS, default=utcnow)

    items: Mapped[list[Item]] = relationship(secondary=document_links)


# --- Bulk uploads -----------------------------------------------------------------------


class UploadGroup(Base):
    __tablename__ = "upload_groups"
    __table_args__ = (
        CheckConstraint(_in("status", GROUP_STATUSES), name="status"),
        CheckConstraint(_in("pairing_rule", ("pattern", "order", "single", "manual")), name="pairing_rule"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    batch_id: Mapped[str] = mapped_column(String(36), index=True)
    pairing_rule: Mapped[str] = mapped_column(String(10))
    label: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(14), default="pending", index=True)
    resulting_item_id: Mapped[int | None] = mapped_column(ForeignKey("items.id", ondelete="SET NULL"))
    created_at: Mapped[dt.datetime] = mapped_column(TS, default=utcnow)
    resolved_at: Mapped[dt.datetime | None] = mapped_column(TS)

    files: Mapped[list[UploadFile]] = relationship(
        back_populates="group", order_by="UploadFile.seq", cascade="all, delete-orphan"
    )


class UploadFile(Base):
    __tablename__ = "upload_files"
    __table_args__ = (CheckConstraint(_in("suggested_role", PHOTO_ROLES), name="suggested_role"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("upload_groups.id", ondelete="CASCADE"), index=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column(Integer, default=0)
    original_filename: Mapped[str] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    phash: Mapped[str | None] = mapped_column(String(16))
    mime: Mapped[str] = mapped_column(String(40))
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    bytes: Mapped[int] = mapped_column(Integer)
    quality: Mapped[dict] = mapped_column(JSON, default=dict)
    suggested_role: Mapped[str] = mapped_column(String(12), default="other")
    duplicate_of_photo_id: Mapped[int | None] = mapped_column(ForeignKey("photos.id", ondelete="SET NULL"))
    duplicate_kind: Mapped[str | None] = mapped_column(String(8))
    created_at: Mapped[dt.datetime] = mapped_column(TS, default=utcnow)

    group: Mapped[UploadGroup] = relationship(back_populates="files")


# --- Operations -------------------------------------------------------------------------


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    actor_type: Mapped[str] = mapped_column(String(10))  # user, token, system
    actor_id: Mapped[int | None] = mapped_column(Integer)
    entity: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[int] = mapped_column(Integer, index=True)
    field: Mapped[str] = mapped_column(String(60))
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    request_id: Mapped[str | None] = mapped_column(String(36))
    at: Mapped[dt.datetime] = mapped_column(TS, default=utcnow, server_default=func.now())


class AppSetting(Base):
    __tablename__ = "app_settings"
    __table_args__ = (UniqueConstraint("owner_id", "key", name="uq_app_settings_owner_key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    key: Mapped[str] = mapped_column(String(60))
    value: Mapped[dict | list | str | int | float | bool | None] = mapped_column(JSON)


# --- Milestone 2: prices, providers, quotas -----------------------------------------------

PROVIDER_KINDS = ("spot", "comps", "catalog", "cert")


class SpotPrice(Base):
    """Every spot price point ever fetched (time series)."""

    __tablename__ = "spot_prices"
    __table_args__ = (
        CheckConstraint(_in("metal", METALS), name="metal"),
        Index("ix_spot_prices_lookup", "metal", "currency", "fetched_at"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    metal: Mapped[str] = mapped_column(String(2))
    currency: Mapped[str] = mapped_column(String(3))
    price_per_toz: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    source: Mapped[str] = mapped_column(String(30))
    source_timestamp: Mapped[dt.datetime | None] = mapped_column(TS)
    fetched_at: Mapped[dt.datetime] = mapped_column(TS, default=utcnow)


class ProviderConfig(Base):
    """Install-wide settings for an external data provider. API keys are stored encrypted."""

    __tablename__ = "provider_configs"
    __table_args__ = (CheckConstraint(_in("kind", PROVIDER_KINDS), name="kind"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    provider_key: Mapped[str] = mapped_column(String(30), unique=True)
    kind: Mapped[str] = mapped_column(String(10))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[int] = mapped_column(Integer, default=100)
    api_key_encrypted: Mapped[str | None] = mapped_column(Text)
    api_key_last4: Mapped[str | None] = mapped_column(String(4))
    quota_cap: Mapped[int | None] = mapped_column(Integer)
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    last_success_at: Mapped[dt.datetime | None] = mapped_column(TS)
    last_error: Mapped[str | None] = mapped_column(Text)
    last_error_at: Mapped[dt.datetime | None] = mapped_column(TS)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[dt.datetime] = mapped_column(TS, default=utcnow, onupdate=utcnow)


VALUATION_KINDS = ("manual", "comps")


class Valuation(Base):
    """A market value for one piece of an item: typed in by the owner, or the median of sold listings they picked."""

    __tablename__ = "valuations"
    __table_args__ = (
        CheckConstraint(_in("kind", VALUATION_KINDS), name="kind"),
        Index("ix_valuations_item_asof", "item_id", "as_of"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(10))
    value_each: Mapped[Decimal] = mapped_column(MONEY)
    currency: Mapped[str] = mapped_column(String(3))
    as_of: Mapped[dt.date] = mapped_column(Date)
    source: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)
    # comps: {"keyword", "basis": "sold"|"total", "count", "low", "median", "high", "listings": [...]}
    details: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[dt.datetime] = mapped_column(TS, default=utcnow)
    item: Mapped[Item] = relationship(back_populates="valuations")


class QuotaPeriod(Base):
    """Request counting for providers with a monthly quota (QuotaManager state)."""

    __tablename__ = "api_quota_periods"
    __table_args__ = (UniqueConstraint("provider_key", "period_start", name="uq_api_quota_periods_provider_start"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    provider_key: Mapped[str] = mapped_column(String(30), index=True)
    period_start: Mapped[dt.datetime] = mapped_column(TS)
    period_end: Mapped[dt.datetime] = mapped_column(TS)
    used: Mapped[int] = mapped_column(Integer, default=0)
    provider_limit: Mapped[int | None] = mapped_column(Integer)
    provider_used: Mapped[int | None] = mapped_column(Integer)
    synced_at: Mapped[dt.datetime | None] = mapped_column(TS)


class ApiCallLog(Base):
    __tablename__ = "api_call_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    provider_key: Mapped[str] = mapped_column(String(30), index=True)
    endpoint: Mapped[str] = mapped_column(String(120))
    context: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20))  # ok, error, skipped
    http_status: Mapped[int | None] = mapped_column(Integer)
    cost: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    detail: Mapped[str | None] = mapped_column(Text)
    at: Mapped[dt.datetime] = mapped_column(TS, default=utcnow, index=True)


class SystemSetting(Base):
    """Install-wide settings (spot polling, thresholds)."""

    __tablename__ = "system_settings"
    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[dict | list | str | int | float | bool | None] = mapped_column(JSON)
