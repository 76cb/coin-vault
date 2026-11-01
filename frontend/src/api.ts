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
  urls: { thumb: string; medium: string; original: string; unedited?: string; edited?: string };
  edits?: Partial<import("./photoEdit").Edits> | null;
  sha256?: string | null;
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
  composition_id?: number | null;
}

export interface ItemValues {
  currency: string;
  melt: string | null;
  melt_by_metal: Record<string, string>;
  melt_missing_spot: string[];
  market: string | null;
  market_each: string | null;
  market_as_of: string | null;
  market_kind: "manual" | "comps" | null;
  market_source: string | null;
  cost: string | null;
  current: string | null;
  gain: string | null;
  rule: string;
  rule_applied: string;
  pure_toz_total: Record<string, string>;
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
  values: ItemValues | null;
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
  melt: string | null;
  current: string | null;
  currency: string;
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
  sha256?: string | null;
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

export interface Composition {
  id: number;
  key: string;
  label: string;
  country: string | null;
  denomination: string | null;
  year_from: number | null;
  year_to: number | null;
  mint_marks: string[] | null;
  metal: Metal;
  fineness: string | null;
  gross_weight_g: string | null;
  pure_toz: string;
  per_face_unit: boolean;
  citation: string | null;
  custom: boolean;
}

export interface Spot {
  metal: Metal;
  label: string;
  price: string | null;
  source: string | null;
  fetched_at: string | null;
  source_timestamp: string | null;
  price_time: string | null;
  stale: boolean;
}
export interface SpotLatest {
  currency: string;
  market_open: boolean;
  stale_after_minutes: number;
  next_poll: string | null;
  metals: Spot[];
}
export interface SpotHistory {
  metal: Metal;
  currency: string;
  interval: "raw" | "hour" | "day";
  holdings_toz: string;
  points: { t: string; price: string }[];
}
export interface ReportItem {
  id: number;
  title: string;
  kind: string;
  status: string;
  quantity: number;
  description: string;
  grade: string | null;
  identifiers: string[];
  metals: string;
  location: string | null;
  acquired_date: string | null;
  cost: string | null;
  current: string | null;
  current_each: string | null;
  basis: string;
  photos: string[];
}
export type ReportOrder = "value" | "location" | "title" | "acquired";
export interface InsuranceReport {
  owner: string;
  date: string;
  generated_at: string;
  currency: string;
  spot: { metal: Metal; label: string; price: string; price_time: string | null }[];
  count: number;
  pieces: number;
  current: string;
  melt: string;
  cost: string;
  cost_items: number;
  unvalued: number;
  by_location: { label: string; count: number; pieces: number; current: string }[];
  items: ReportItem[];
}
export interface ValuePoint {
  day: string; // YYYY-MM-DD
  value: string;
  paid: string;
  items: number;
  pieces: number;
  unvalued: number;
}
export interface ValueHistory {
  currency: string;
  start: string | null;
  end: string;
  step_days: number;
  first_spot: string | null;
  clipped: boolean;
  undated: number;
  no_cost: number;
  added: { count: number; amount: string };
  sold: { count: number; amount: string };
  points: ValuePoint[];
}
export interface Bucket {
  key: string;
  label: string;
  count: number;
  pieces: number;
  pure_toz: string;
  melt: string;
  cost: string;
  current: string;
}
export interface Summary {
  currency: string;
  spot: SpotLatest;
  totals: {
    item_count: number;
    pieces: number;
    melt: string;
    market: string;
    market_items: number;
    valued_at_market: number;
    cost: string;
    cost_estimated: string;
    current: string;
    gain: string;
    gain_items: number;
    cost_unknown_items: number;
    estimated_cost_items: number;
    no_value_items: number;
  };
  pure_toz: Record<string, string>;
  by_metal: Bucket[];
  by_type: Bucket[];
  by_location: Bucket[];
  market_values_available: boolean;
}

export interface AppSettings {
  base_currency: string;
  currencies: string[];
  spot_poll_minutes: number;
  spot_stale_minutes: number;
  spot_pause_weekends: boolean;
  encryption_ready: boolean;
  scheduler_running: boolean;
}
export interface ProviderUsage {
  used: number;
  cap: number | null;
  provider_limit: number | null;
  provider_used: number | null;
  remaining: number | null;
  period_start: string;
  period_end: string;
  synced_at: string | null;
}
export interface Provider {
  key: string;
  label: string;
  kind: "spot" | "comps" | string;
  note: string;
  docs_url: string;
  key_url: string | null;
  available_from: number;
  needs_key: boolean;
  key_set: boolean;
  key_last4: string | null;
  enabled: boolean;
  priority: number;
  quota_cap: number | null;
  quota_period: string | null;
  usage: ProviderUsage | null;
  last_success_at: string | null;
  last_error: string | null;
  last_error_at: string | null;
  consecutive_failures: number;
}
export interface ProviderCall {
  at: string;
  endpoint: string;
  context: string | null;
  status: string;
  http_status: number | null;
  cost: number;
  duration_ms: number | null;
  detail: string | null;
}
export interface DayCount {
  date: string;
  requests: number;
  calls: number;
  errors: number;
}

export interface CompListing {
  item_id: string;
  title: string | null;
  url: string;
  thumbnail_url: string | null;
  condition: string | null;
  buying_format: string | null;
  ended_at: string | null;
  sold_price: string | null;
  shipping_price: string | null;
  total_price: string | null;
  currency: string | null;
  best_offer: boolean;
}
export interface CompsSearch {
  keyword: string;
  total_results: string | null;
  has_more: boolean;
  currency: string;
  listings: CompListing[];
  other_currency: number;
  stats: { count: number; low: string | null; median: string | null; high: string | null };
  requests_used: number | null;
  requests_limit: number | null;
}
export interface Valuation {
  id: number;
  item_id: number;
  pinned: boolean; // the owner chose this one
  in_use: boolean; // the item's market value comes from it
  kind: "manual" | "comps";
  value_each: string;
  currency: string;
  as_of: string;
  source: string | null;
  notes: string | null;
  details: { keyword?: string; basis?: "sold" | "total"; count?: number; low?: string; median?: string; high?: string; listings?: CompListing[] } | null;
  created_at: string;
}

export interface AiStatus {
  ready: boolean;
  model: string | null;
}
export interface AiSettings extends AiStatus {
  url: string;
}
export interface AiModel {
  name: string;
  size: number | null;
  parameter_size: string | null;
  quantization: string | null;
  vision: boolean;
}
export interface AiCheck {
  url: string;
  version: string;
  models: AiModel[];
}
export interface AiPhotoRef {
  sha256: string;
  role: PhotoRole;
}
export interface AiMatch {
  id: number;
  title: string;
  thumb: string | null;
  quantity: number;
  why: string;
}
export interface AiIdentify {
  model: string;
  seconds: number;
  load_seconds: number;
  confidence: "high" | "medium" | "low";
  title: string;
  kind: ItemType;
  country: string | null;
  denomination: string | null;
  year: number | null;
  mint_mark: string | null;
  series: string | null;
  weight_text: string | null;
  holder: { service: string | null; grade: string | null; cert_number: string | null; pcgs_number: string | null; label_text: string | null } | null;
  barcodes: { text: string; format: string }[];
  notes: string | null;
  described: Described;
  same_coin: AiMatch[];
  same_photos: AiMatch[];
}
export interface AiGrade {
  model: string;
  seconds: number;
  low: string;
  high: string;
  low_number: number;
  high_number: number;
  summary: string;
  wear: string | null;
  surfaces: string | null;
  marks?: string[];
  problems: string[];
  photo_advice: string | null;
}

export interface Described {
  item_type: ItemType;
  title: string;
  quantity: number;
  metal: Metal | null;
  details: Record<string, string | number | boolean>;
  condition: {
    grading: "raw" | "slabbed";
    grading_service: string | null;
    grade_text: string | null;
    sheldon_grade: number | null;
    designations: string[];
    details_reason: string | null;
    cert_number?: string | null;
  } | null;
  recognized: string[];
  notes: string[];
  compositions: (Composition & { score: number })[];
}

export interface PcgsCoin {
  cert_no: string | null;
  pcgs_no: string | null;
  name: string | null;
  year: number | null;
  denomination: string | null;
  mint_mark: string | null;
  country: string | null;
  grade: string | null;
  designation: string | null;
  metal_content: string | null;
  weight_g: string | null;
  price_guide: string | null;
  population: number | null;
  pop_higher: number | null;
  coinfacts_link: string | null;
  series: string | null;
  images: { thumbnail: string | null; fullsize: string | null }[];
}

export interface PcgsLookup {
  coin: PcgsCoin;
  item_type: ItemType;
  title: string;
  details: Record<string, string | number | boolean>;
  condition: {
    grading: "raw" | "slabbed";
    grading_service: string | null; // PCGS or NGC for a slab; null for a coin type looked up by grade
    cert_number: string | null;
    grade_text: string | null;
    sheldon_grade: number | null;
    designations: string[];
    details_reason: null;
  };
  metal: { metal: Metal; gross_weight_g: string; fineness: string } | null;
  currency_note: string | null;
}

export interface NumistaHit {
  id: number;
  title: string | null;
  issuer: string | null;
  min_year: number | null;
  max_year: number | null;
  obverse_thumbnail: string | null;
  reverse_thumbnail: string | null;
}

export interface NumistaIssue {
  id: number;
  year: number | null;
  gregorian_year: number | null;
  mint_letter: string | null;
  mintage: number | null;
  comment: string | null;
}

export interface NumistaType {
  id: number;
  url: string | null;
  title: string;
  issuer: string | null;
  min_year: number | null;
  max_year: number | null;
  denomination: string | null;
  composition: string | null;
  weight_g: string | null;
  size_mm: string | null;
  references: string[];
  obverse_thumb: string | null;
  reverse_thumb: string | null;
  issues: NumistaIssue[];
  item_type: ItemType;
  details: Record<string, string | number>;
  metal: { metal: Metal; gross_weight_g: string; fineness: string } | null;
}

export interface LibraryFile {
  sha256: string;
  urls: { thumb: string; medium: string; original: string };
  width: number;
  height: number;
  bytes: number;
  filename: string | null;
  created_at: string;
  items: { item_id: number; title: string; photo_id: number; role: PhotoRole; is_cover: boolean }[];
  waiting_upload: boolean;
  suggested_role: PhotoRole | null; // the side a bulk upload guessed from the file name
}
/** Photos chosen on the Photos page for a new item, carried to Add item. */
export interface PickedPhoto {
  sha256: string;
  thumb: string;
  filename: string | null;
  role: PhotoRole;
}

export interface BackupEntry {
  name: string;
  created_at: string;
  reason: "nightly" | "manual" | string;
  counts: { items?: number; photos?: number; documents?: number; valuations?: number; users?: number };
  files: number;
  database_bytes: number;
  media_bytes: number;
  new_files: number;
  verified: boolean;
  seconds: number | null;
  download_bytes: number;
}

export interface UpdateSource { checked: number; changed: number; failed: number; skipped: number; stopped: string | null }
export interface ValueUpdates {
  enabled: boolean;
  day: "mon" | "tue" | "wed" | "thu" | "fri" | "sat" | "sun";
  time: string;
  timezone: string;
  next_run: string | null;
  running: boolean;
  tracked_pcgs: number;
  tracked_numista: number;
  last: { started_at: string; finished_at: string | null; ok: boolean; pcgs?: UpdateSource; numista?: UpdateSource; errors: string[] } | null;
}
export interface BackupStatus {
  enabled: boolean;
  time: string;
  timezone: string;
  folder: string;
  free_bytes: number | null;
  next_run: string | null;
  last: { at: string | null; ok: boolean | null; name: string | null; error: string | null } | null;
  backups: BackupEntry[];
}

/** A PCGS cert number on its own ("12345678", "cert #12345678", "PCGS 12345678"), or null. */
/** What to look up at PCGS: a cert number, a PCGS number and grade, or a PCGS or NGC holder's barcode. */
export type PcgsQuery = { cert_no: string } | { pcgs_no: string; grade: string } | { barcode: string; service: "PCGS" | "NGC" };

/** "9801 MS65", "PCGS #9801 64+": a PCGS number and grade. Needs the grade's letters, or "PCGS"/"#" in front. */
export function pcgsNumberGrade(text: string): { pcgs_no: string; grade: string } | null {
  const m = text.trim().match(/^(pcgs\s*(?:no\.?|number)?\s*#?|#)?\s*(\d{2,7})\s*[,/ ]\s*((?:MS|PR|PF|SP|AU|XF|EF|VF|VG|AG|F|G)?)\s*-?\s*(\d{1,2}\+?)$/i);
  if (!m || (!m[1] && !m[3]) || Number(m[4].replace("+", "")) > 70) return null;
  return { pcgs_no: m[2], grade: `${m[3].toUpperCase()}${m[4]}` };
}

export function certNumber(text: string): string | null {
  const m = text.trim().match(/^(?:pcgs\s*)?(?:cert(?:ificate)?\s*(?:#|no\.?|number)?\s*)?#?\s*(\d{6,10})$/i);
  return m ? m[1] : null;
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
  createItemFromLibrary: (item: unknown, photos: { sha256: string; role: PhotoRole }[]) =>
    request<Item>("POST", `${A}/library/create-item`, { item, photos }),
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
  backups: () => request<BackupStatus>("GET", `${A}/backups`),
  backupNow: () => request<BackupEntry>("POST", `${A}/backups`),
  valueUpdates: () => request<ValueUpdates>("GET", `${A}/value-updates`),
  runValueUpdates: () => request<ValueUpdates>("POST", `${A}/value-updates`),
  valueUpdateSettings: (body: { enabled: boolean; day: ValueUpdates["day"]; time: string }) =>
    request<ValueUpdates>("PUT", `${A}/value-updates/settings`, body),
  backupSettings: (body: { enabled: boolean; time: string }) => request<BackupStatus>("PUT", `${A}/backups/settings`, body),
  deleteBackup: (name: string) => request<void>("DELETE", `${A}/backups/${encodeURIComponent(name)}`),
  backupDownloadUrl: (name: string) => `${A}/backups/${encodeURIComponent(name)}/download`,
  library: (show: "all" | "on_items" | "not_on_items", page = 1, perPage = 60) =>
    request<{ total: number; files: LibraryFile[] }>("GET", `${A}/library?${new URLSearchParams({ show, page: String(page), per_page: String(perPage) })}`),
  deleteFromLibrary: (sha256s: string[]) =>
    request<{ deleted: number; photos_removed: number; uploads_removed: number }>("POST", `${A}/library/delete`, { sha256s }),
  addFromLibrary: (itemId: number, body: { sha256: string; role: PhotoRole; make_cover: boolean }) =>
    request<Photo>("POST", `${A}/items/${itemId}/photos/from-library`, body),
  findCoin: (photoId: number, frame: { rotate: number; flip: boolean; straighten: number }) =>
    request<{ crop: { x: number; y: number; w: number; h: number } }>("POST", `${A}/photos/${photoId}/find-coin`, frame),
  setPhotoEdits: (id: number, edits: unknown) => request<Photo>("PUT", `${A}/photos/${id}/edits`, { edits }),
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

  spotLatest: () => request<SpotLatest>("GET", `${A}/prices/spot/latest`),
  refreshSpot: () => request<{ ok: boolean; source: string | null; old_metals: Metal[]; errors: string[]; latest: SpotLatest }>("POST", `${A}/prices/spot/refresh`),
  spotHistory: (metal: Metal, days: number) => request<SpotHistory>("GET", `${A}/prices/spot/history?metal=${metal}&days=${days}`),
  summary: () => request<Summary>("GET", `${A}/portfolio/summary`),
  report: (params: Record<string, string>) => request<InsuranceReport>("GET", `${A}/report?${new URLSearchParams(params)}`),
  exportCsvUrl: (params: Record<string, string>) => `${A}/export/items.csv?${new URLSearchParams(params)}`,
  valueHistory: (days: number, type?: ItemType | "", metal?: Metal | "") => {
    const q = new URLSearchParams({ days: String(days) });
    if (type) q.set("type", type);
    if (metal) q.set("metal", metal);
    return request<ValueHistory>("GET", `${A}/portfolio/history?${q}`);
  },

  describe: (text: string) => request<Described>("POST", `${A}/items/describe`, { text }),
  compositions: (params: Record<string, string> = {}) => request<Composition[]>("GET", `${A}/compositions?${new URLSearchParams(params)}`),
  matchCompositions: (params: Record<string, string>) =>
    request<(Composition & { score: number })[]>("GET", `${A}/compositions/match?${new URLSearchParams(params)}`),
  createComposition: (body: unknown) => request<Composition>("POST", `${A}/compositions`, body),
  deleteComposition: (id: number) => request<void>("DELETE", `${A}/compositions/${id}`),

  numistaSearch: (q: string, year?: string) =>
    request<{ count: number; types: NumistaHit[] }>("GET", `${A}/numista/search?${new URLSearchParams(year ? { q, year } : { q })}`),
  numistaType: (id: number) => request<NumistaType>("GET", `${A}/numista/types/${id}`),
  numistaEstimate: (itemId: number) => request<Valuation>("POST", `${A}/items/${itemId}/numista/estimate`),
  aiStatus: () => request<AiStatus>("GET", `${A}/ai`),
  aiSettings: () => request<AiSettings>("GET", `${A}/ai/settings`),
  saveAiSettings: (body: { url: string; model: string }) => request<AiSettings>("PUT", `${A}/ai/settings`, body),
  aiCheck: (url: string) => request<AiCheck>("POST", `${A}/ai/check`, { url }),
  aiIdentify: (photos: AiPhotoRef[], itemId?: number) => request<AiIdentify>("POST", `${A}/ai/identify`, { photos, item_id: itemId ?? null }),
  aiGrade: (photos: AiPhotoRef[], itemId?: number) => request<AiGrade>("POST", `${A}/ai/grade`, { photos, item_id: itemId ?? null }),
  pcgsLookup: (q: PcgsQuery) => request<PcgsLookup>("POST", `${A}/pcgs/lookup`, q),
  pcgsReadBarcode: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return request<{ text: string; format: string }[]>("POST", `${A}/pcgs/read-barcode`, fd);
  },
  pcgsPriceGuide: (itemId: number) => request<Valuation>("POST", `${A}/items/${itemId}/pcgs/price-guide`),

  valuations: (itemId: number) => request<Valuation[]>("GET", `${A}/items/${itemId}/valuations`),
  addValuation: (itemId: number, body: unknown) => request<Valuation>("POST", `${A}/items/${itemId}/valuations`, body),
  useValuation: (id: number, use: boolean) => request<Valuation[]>("PUT", `${A}/valuations/${id}/use`, { use }),
  deleteValuation: (id: number) => request<void>("DELETE", `${A}/valuations/${id}`),
  compsKeyword: (itemId: number) => request<{ keyword: string }>("GET", `${A}/items/${itemId}/comps/keyword`),
  searchComps: (itemId: number, body: { keyword: string; sold_within_days: number | null; condition: string; exact_match: boolean }) =>
    request<CompsSearch>("POST", `${A}/items/${itemId}/comps/search`, body),

  settings: () => request<AppSettings>("GET", `${A}/settings`),
  patchSettings: (body: Partial<AppSettings>) => request<AppSettings>("PATCH", `${A}/settings`, body),
  providers: () => request<Provider[]>("GET", `${A}/settings/providers`),
  updateProvider: (key: string, body: { api_key?: string | null; enabled?: boolean; priority?: number; quota_cap?: number }) =>
    request<Provider>("PUT", `${A}/settings/providers/${key}`, body),
  testProvider: (key: string) => request<{ ok: boolean; message: string; provider: Provider }>("POST", `${A}/settings/providers/${key}/test`),
  providerUsage: (key: string) => request<{ provider: Provider; days: DayCount[] }>("GET", `${A}/settings/providers/${key}/usage`),
  providerCalls: (key: string, limit = 20) => request<ProviderCall[]>("GET", `${A}/settings/providers/${key}/calls?limit=${limit}`),
};

export function money(v: string | null | undefined, currency = "USD"): string {
  if (v === null || v === undefined || v === "") return "—";
  const n = Number(v);
  return Number.isFinite(n) ? n.toLocaleString(undefined, { style: "currency", currency }) : v;
}

export function compactMoney(v: string | number | null | undefined, currency = "USD"): string {
  if (v === null || v === undefined || v === "") return "—";
  const n = Number(v);
  if (!Number.isFinite(n)) return String(v);
  return n.toLocaleString(undefined, { style: "currency", currency, notation: Math.abs(n) >= 100000 ? "compact" : "standard", minimumFractionDigits: Math.abs(n) >= 100 ? 0 : 2, maximumFractionDigits: Math.abs(n) >= 100 ? 0 : 2 });
}

/** "3 minutes ago" style, for timestamps in the past. */
export function ago(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return "never";
  // Timestamps without an offset are UTC (SQLite drops it).
  const t = /[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`;
  const s = Math.round((now - new Date(t).getTime()) / 1000);
  const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  if (Math.abs(s) < 60) return "just now";
  if (Math.abs(s) < 3600) return rtf.format(-Math.round(s / 60), "minute");
  if (Math.abs(s) < 86400) return rtf.format(-Math.round(s / 3600), "hour");
  return rtf.format(-Math.round(s / 86400), "day");
}

export const RULE_LABELS: Record<string, string> = {
  max: "the higher of melt and market value",
  melt: "melt value",
  market: "market value",
  cost: "what you paid",
};

export function ozt(v: string | null | undefined): string {
  if (!v) return "—";
  const n = Number(v);
  return `${n.toLocaleString(undefined, { maximumFractionDigits: 4 })} ozt`;
}
