// Thin typed client for the Coin Vault API. Session cookie + CSRF header on writes.

export type ItemType = "coin" | "bullion" | "bar" | "banknote" | "lot" | "other";
export type ItemStatus = "owned" | "for_sale" | "sold";
export type CostStatus = "known" | "estimated" | "unknown";
export type PhotoRole = "obverse" | "reverse" | "edge" | "slab_front" | "slab_back" | "other";
export type Metal = "Au" | "Ag" | "Pt" | "Pd";

export const ITEM_TYPE_LABELS: Record<ItemType, string> = {
  coin: "Coin",
  bullion: "Bullion coin or round",
  bar: "Bar",
  banknote: "Banknote",
  lot: "Junk / constant-content lot",
  other: "Other",
};
export const STATUS_LABELS: Record<ItemStatus, string> = { owned: "Owned", for_sale: "For sale", sold: "Sold" };
export const ROLE_LABELS: Record<PhotoRole, string> = {
  obverse: "Obverse",
  reverse: "Reverse",
  edge: "Edge",
  slab_front: "Slab front",
  slab_back: "Slab back",
  other: "Other",
};
export const METAL_LABELS: Record<Metal, string> = { Au: "Gold", Ag: "Silver", Pt: "Platinum", Pd: "Palladium" };

export interface User {
  id: number;
  username: string;
  is_admin: boolean;
  base_currency: string;
}
export interface Me {
  user: User;
  auth: string;
  csrf_token: string | null;
  scopes: string[];
}

export interface QualityIssue {
  check: string;
  advice: string;
}
export interface Quality {
  verdict?: "pass" | "warn";
  issues?: QualityIssue[];
  gps_removed?: boolean;
  blur_score?: number;
  glare_fraction?: number;
  min_side_px?: number;
}

export interface Photo {
  id: number;
  item_id: number;
  role: PhotoRole;
  sort_order: number;
  width: number;
  height: number;
  bytes: number;
  quality: Quality;
  original_filename: string | null;
  urls: { thumb: string; medium: string; original: string };
  duplicate_of_item_id?: number | null;
  duplicate_kind?: "exact" | "similar" | null;
}

export interface Condition {
  grading: "raw" | "slabbed";
  sheldon_grade: number | null;
  grade_text: string | null;
  grading_service: string | null;
  cert_number: string | null;
  designations: string[];
  details_reason: string | null;
}

export interface MetalContent {
  id?: number;
  metal: Metal;
  gross_weight_g: string | null;
  fineness: string | null;
  pure_toz: string | null;
  source?: "reference" | "computed" | "override";
}

export interface DocSummary {
  id: number;
  kind: string;
  title: string;
  doc_date: string | null;
  mime: string;
  url: string;
}

export interface Item {
  id: number;
  item_type: ItemType;
  title: string;
  quantity: number;
  status: ItemStatus;
  location_id: number | null;
  location_path: string | null;
  acquired_date: string | null;
  purchase_price: string | null;
  purchase_fees: string | null;
  cost_basis: string | null;
  cost_basis_status: CostStatus;
  purchase_source: string | null;
  notes: string | null;
  valuation_rule: string;
  sale_date: string | null;
  sale_price: string | null;
  sale_fees: string | null;
  sale_venue: string | null;
  condition: Condition | null;
  details: Record<string, unknown>;
  metal_content: MetalContent[];
  pure_toz_per_unit: Record<string, string>;
  tags: string[];
  cover_photo_id: number | null;
  cover_thumb_url: string | null;
  photos: Photo[];
  documents: DocSummary[];
  version: number;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
}

export interface ItemListEntry {
  id: number;
  item_type: ItemType;
  title: string;
  quantity: number;
  status: ItemStatus;
  location_path: string | null;
  year: number | null;
  country: string | null;
  grade: string | null;
  cost_basis: string | null;
  cost_basis_status: CostStatus;
  tags: string[];
  cover_thumb_url: string | null;
  photo_count: number;
  updated_at: string;
  deleted_at: string | null;
}

export interface ItemPage {
  items: ItemListEntry[];
  total: number;
  page: number;
  page_size: number;
}

export interface Location {
  id: number;
  name: string;
  parent_id: number | null;
  notes: string | null;
  path: string;
  item_count: number;
}
export interface Tag {
  id: number;
  name: string;
  item_count: number;
}

export interface UploadFile {
  id: number;
  seq: number;
  original_filename: string;
  role: PhotoRole;
  width: number;
  height: number;
  bytes: number;
  quality: Quality;
  duplicate_of_photo_id: number | null;
  duplicate_of_item_id: number | null;
  duplicate_kind: "exact" | "similar" | null;
  urls: { thumb: string; medium: string; original: string };
}
export interface UploadGroup {
  id: number;
  batch_id: string;
  pairing_rule: "pattern" | "order" | "single" | "manual";
  label: string | null;
  status: string;
  resulting_item_id: number | null;
  files: UploadFile[];
}
export interface UploadResult {
  batch_id: string;
  groups: UploadGroup[];
  rejected: { filename: string; reason: string }[];
}

export interface ApiToken {
  id: number;
  name: string;
  prefix: string;
  scopes: string[];
  created_at: string;
  last_used_at: string | null;
  expires_at: string | null;
  revoked_at: string | null;
  token?: string;
}

export interface DocumentFull extends DocSummary {
  bytes: number;
  original_filename: string | null;
  item_ids: number[];
}

// --- Transport -----------------------------------------------------------------------

let csrfToken: string | null = null;
export function setCsrf(token: string | null) {
  csrfToken = token;
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function describe(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d: { loc?: (string | number)[]; msg?: string }) => {
        const field = (d.loc ?? []).filter((p) => p !== "body").join(" › ");
        return field ? `${field}: ${d.msg}` : d.msg;
      })
      .join("; ");
  }
  return "Request failed";
}

export async function request<T>(method: string, url: string, body?: unknown, headers: Record<string, string> = {}): Promise<T> {
  const h: Record<string, string> = { ...headers };
  if (method !== "GET" && csrfToken) h["X-CSRF-Token"] = csrfToken;
  let payload: BodyInit | undefined;
  if (body instanceof FormData) payload = body;
  else if (body !== undefined) {
    h["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  const res = await fetch(url, { method, headers: h, body: payload, credentials: "same-origin" });
  if (res.status === 204) return undefined as T;
  const data = res.headers.get("content-type")?.includes("json") ? await res.json() : null;
  if (!res.ok) {
    if (res.status === 401 && !url.endsWith("/auth/login")) window.dispatchEvent(new Event("cv:signed-out"));
    throw new ApiError(res.status, describe(data?.detail) || res.statusText);
  }
  return data as T;
}

const A = "/api/v1";
export const api = {
  me: () => request<Me>("GET", `${A}/auth/me`),
  login: (username: string, password: string) => request<Me>("POST", `${A}/auth/login`, { username, password }),
  logout: () => request<void>("POST", `${A}/auth/logout`),
  changePassword: (current_password: string, new_password: string) =>
    request<void>("POST", `${A}/auth/password`, { current_password, new_password }),
  tokens: () => request<ApiToken[]>("GET", `${A}/auth/tokens`),
  createToken: (name: string, scopes: string[], expires_in_days: number | null) =>
    request<ApiToken>("POST", `${A}/auth/tokens`, { name, scopes, expires_in_days }),
  revokeToken: (id: number) => request<void>("DELETE", `${A}/auth/tokens/${id}`),

  items: (params: Record<string, string>) => request<ItemPage>("GET", `${A}/items?${new URLSearchParams(params)}`),
  item: (id: number) => request<Item>("GET", `${A}/items/${id}`),
  createItem: (body: unknown) => request<Item>("POST", `${A}/items`, body),
  updateItem: (id: number, version: number, body: unknown) =>
    request<Item>("PATCH", `${A}/items/${id}`, body, { "If-Match": String(version) }),
  deleteItem: (id: number) => request<void>("DELETE", `${A}/items/${id}`),
  restoreItem: (id: number) => request<Item>("POST", `${A}/items/${id}/restore`),
  audit: (id: number) =>
    request<{ id: number; field: string; old_value: string | null; new_value: string | null; at: string; actor_type: string }[]>(
      "GET",
      `${A}/items/${id}/audit`,
    ),

  uploadPhotos: (itemId: number, files: File[], roles?: PhotoRole[]) => {
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f));
    roles?.forEach((r) => fd.append("roles", r));
    return request<Photo[]>("POST", `${A}/items/${itemId}/photos`, fd);
  },
  setPhotoRole: (id: number, role: PhotoRole) => request<Photo>("PATCH", `${A}/photos/${id}`, { role }),
  reorderPhotos: (itemId: number, photo_ids: number[]) =>
    request<Photo[]>("PUT", `${A}/items/${itemId}/photos/order`, { photo_ids }),
  setCover: (itemId: number, photo_id: number) => request<void>("PUT", `${A}/items/${itemId}/cover`, { photo_id }),
  deletePhoto: (id: number) => request<void>("DELETE", `${A}/photos/${id}`),

  uploadDocument: (file: File, fields: { kind: string; title?: string; doc_date?: string; item_ids?: number[] }) => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("kind", fields.kind);
    if (fields.title) fd.append("title", fields.title);
    if (fields.doc_date) fd.append("doc_date", fields.doc_date);
    fields.item_ids?.forEach((id) => fd.append("item_ids", String(id)));
    return request<DocumentFull>("POST", `${A}/documents`, fd);
  },
  setDocumentLinks: (id: number, item_ids: number[]) => request<DocumentFull>("PUT", `${A}/documents/${id}/links`, { item_ids }),
  deleteDocument: (id: number) => request<void>("DELETE", `${A}/documents/${id}`),

  bulkUpload: (files: File[]) => {
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f));
    return request<UploadResult>("POST", `${A}/uploads`, fd);
  },
  uploadGroups: () => request<UploadGroup[]>("GET", `${A}/uploads/groups?status=pending`),
  patchGroup: (id: number, body: { label?: string | null; roles?: Record<number, PhotoRole> }) =>
    request<UploadGroup>("PATCH", `${A}/uploads/groups/${id}`, body),
  splitGroup: (id: number) => request<UploadGroup[]>("POST", `${A}/uploads/groups/${id}/split`),
  mergeGroups: (group_ids: number[]) => request<UploadGroup>("POST", `${A}/uploads/groups/merge`, { group_ids }),
  attachGroup: (id: number, item_id: number) => request<Item>("POST", `${A}/uploads/groups/${id}/attach`, { item_id }),
  createItemFromGroup: (id: number, item: unknown) =>
    request<Item>("POST", `${A}/uploads/groups/${id}/create-item`, { item }),
  discardGroup: (id: number) => request<UploadGroup>("POST", `${A}/uploads/groups/${id}/discard`),

  locations: () => request<Location[]>("GET", `${A}/locations`),
  createLocation: (name: string, parent_id: number | null) =>
    request<Location>("POST", `${A}/locations`, { name, parent_id }),
  updateLocation: (id: number, name: string, parent_id: number | null) =>
    request<Location>("PATCH", `${A}/locations/${id}`, { name, parent_id }),
  deleteLocation: (id: number) => request<void>("DELETE", `${A}/locations/${id}`),
  tags: () => request<Tag[]>("GET", `${A}/tags`),
  renameTag: (id: number, name: string) => request<Tag>("PATCH", `${A}/tags/${id}`, { name }),
  deleteTag: (id: number) => request<void>("DELETE", `${A}/tags/${id}`),
};

export function money(v: string | null | undefined, currency = "USD"): string {
  if (v === null || v === undefined || v === "") return "—";
  const n = Number(v);
  return Number.isFinite(n) ? n.toLocaleString(undefined, { style: "currency", currency }) : v;
}

export function ozt(v: string | null | undefined): string {
  if (!v) return "—";
  const n = Number(v);
  return `${n.toLocaleString(undefined, { maximumFractionDigits: 4 })} ozt`;
}
