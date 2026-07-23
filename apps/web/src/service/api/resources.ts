import { request } from "../request"

export type ResourceLibrarySection =
  | "overview"
  | "resources"
  | "inventory"
  | "locations"
  | "bookings"
  | "reminders"
  | "events"
  | "types"

export interface ResourceTypeRevision {
  id: string
  revision: number
  protocol_id: string
  protocol_version_id: string
  protocol_version: string
  capabilities: Record<string, boolean>
  booking_policy: "none" | "auto" | "approval" | "authorized"
  schema_hash: string
}

export interface ResourceType {
  id: string
  lab_id: string
  code: string
  name: string
  description: string
  current_revision_id: string | null
  current_revision?: ResourceTypeRevision | null
  archived_at: string | null
}

export interface ResourceDefinitionVersion {
  id: string
  protocol_id: string
  protocol_uid: string
  protocol_name: string
  project_id: string
  project_name: string
  version: string
  is_latest: boolean
  registered: boolean
  created_at: string
}

export interface ResourceItem {
  id: string
  lab_id: string
  resource_type_id: string
  current_revision_id: string | null
  name: string
  code: string
  status: "active" | "quarantined" | "depleted" | "retired" | "archived"
  visibility: "lab" | "restricted"
  data?: Record<string, unknown>
  revision?: number
  created_at: string
  updated_at: string
}

export interface ResourceDetail extends ResourceItem {
  current_revision: {
    id: string
    revision: number
    data: Record<string, unknown>
    revision_kind: string
    reason: string
    created_at: string
  } | null
  revisions: Array<Record<string, unknown>>
  lots: Array<Record<string, unknown>>
  containers: Array<Record<string, unknown>>
  inventory_events: InventoryEvent[]
  record_links: Array<Record<string, unknown>>
  lineage: Array<Record<string, unknown>>
  equipment_service_events: Array<Record<string, unknown>>
}

export interface InventoryEvent {
  id: string
  kind: string
  resource_id: string
  container_id: string | null
  from_container_id: string | null
  to_container_id: string | null
  quantity: string
  unit: string
  on_hand_before: string | null
  on_hand_after: string | null
  reserved_before: string | null
  reserved_after: string | null
  reason: string
  created_at: string
}

export interface ResourceLocation {
  id: string
  lab_id: string
  parent_id: string | null
  code: string
  name: string
  kind: string
  path: string
  visibility: "lab" | "restricted"
}

export interface EquipmentBooking {
  id: string
  resource_id: string
  user_id: string
  starts_at: string
  ends_at: string
  status: "pending" | "approved" | "rejected" | "cancelled" | "completed"
  approval_policy: string
  purpose: string
}

export interface ResourceNotification {
  id: string
  kind: string
  title: string
  message: string
  target_type: string
  target_id: string
  due_at: string | null
  read_at: string | null
  created_at: string
}

export interface ResourceOverview {
  resources: number
  depleted: number
  expiring_within_30_days: number
  unread_notifications: number
  active_bookings: number
}

export interface ResourceTemplate {
  id: string
  name: string
  name_en: string
  capabilities: Record<string, boolean>
  aimd: string
}

function libraryUrl(labId: string, path = "") {
  return `/labs/${labId}/resource-library${path}`
}

async function getData<T>(options: Parameters<typeof request<T>>[0]): Promise<T> {
  const { data, error } = await request<T>(options)
  if (error)
    throw error
  if (data === null)
    throw new Error("Resource library returned no data")
  return data
}

export function fetchResourceOverview(labId: string) {
  return getData<ResourceOverview>({ url: libraryUrl(labId, "/overview") })
}

export function fetchResourceDefinitionVersions(labId: string) {
  return getData<{ items: ResourceDefinitionVersion[] }>({
    url: libraryUrl(labId, "/definition-versions"),
  })
}

export function fetchResourceTypes(labId: string) {
  return getData<{ items: ResourceType[] }>({ url: libraryUrl(labId, "/types") })
}

export function fetchResourceTemplates(labId: string) {
  return getData<{ templates: ResourceTemplate[] }>({ url: libraryUrl(labId, "/templates") })
}

export function registerResourceType(
  labId: string,
  payload: {
    protocol_version_id: string
    code: string
    name: string
    description?: string
    capabilities: Record<string, boolean>
    booking_policy: string
  },
) {
  return getData<ResourceType>({
    url: libraryUrl(labId, "/types"),
    method: "POST",
    data: payload,
  })
}

export function reviseResourceType(
  labId: string,
  resourceTypeId: string,
  payload: {
    protocol_version_id: string
    code: string
    name: string
    description?: string
    capabilities: Record<string, boolean>
    booking_policy: string
  },
) {
  return getData<ResourceType>({
    url: libraryUrl(labId, `/types/${resourceTypeId}/revisions`),
    method: "POST",
    data: payload,
  })
}

export interface ResourceMigrationPreview {
  dry_run: true
  ready: number
  needs_review: number
  items: Array<{
    resource_id: string
    resource_revision: number
    ready: boolean
    status: string
    issues: Array<{ path?: string, message: string }>
    not_collected: string[]
  }>
}

export function previewResourceTypeMigration(
  labId: string,
  resourceTypeId: string,
) {
  return getData<ResourceMigrationPreview>({
    url: libraryUrl(labId, `/types/${resourceTypeId}/migration-jobs`),
    method: "POST",
    data: {
      dry_run: true,
      idempotency_key: crypto.randomUUID(),
    },
  })
}

export function startResourceTypeMigration(
  labId: string,
  resourceTypeId: string,
  idempotencyKey: string,
) {
  return getData<Record<string, unknown>>({
    url: libraryUrl(labId, `/types/${resourceTypeId}/migration-jobs`),
    method: "POST",
    data: {
      dry_run: false,
      idempotency_key: idempotencyKey,
    },
  })
}

export function fetchResources(
  labId: string,
  params: {
    q?: string
    resource_type_id?: string | null
    status?: string | null
    field_path?: string
    field_value?: string
    numeric_min?: string
    numeric_max?: string
    page?: number
    page_size?: number
  } = {},
) {
  return getData<{ items: ResourceItem[], page: number, page_size: number }>({
    url: libraryUrl(labId, "/resources"),
    params,
  })
}

export function fetchResource(labId: string, resourceId: string) {
  return getData<ResourceDetail>({
    url: libraryUrl(labId, `/resources/${resourceId}`),
  })
}

export function createResource(
  labId: string,
  payload: {
    resource_type_id: string
    name: string
    code: string
    data: Record<string, unknown>
    status?: string
    visibility?: "lab" | "restricted"
    reason?: string
  },
) {
  return getData<ResourceItem>({
    url: libraryUrl(labId, "/resources"),
    method: "POST",
    data: payload,
  })
}

export function reviseResource(
  labId: string,
  resourceId: string,
  payload: {
    data: Record<string, unknown>
    name?: string
    status?: string
    visibility?: "lab" | "restricted"
    reason: string
  },
) {
  return getData<ResourceItem>({
    url: libraryUrl(labId, `/resources/${resourceId}/revisions`),
    method: "POST",
    data: payload,
  })
}

export function createResourceLot(
  labId: string,
  resourceId: string,
  payload: {
    code: string
    supplier?: string
    received_at?: string
    expires_at?: string
    data?: Record<string, unknown>
  },
) {
  return getData<Record<string, unknown>>({
    url: libraryUrl(labId, `/resources/${resourceId}/lots`),
    method: "POST",
    data: payload,
  })
}

export function createResourceContainer(
  labId: string,
  resourceId: string,
  payload: {
    code: string
    lot_id?: string | null
    location_id?: string | null
    unit: string
    data?: Record<string, unknown>
  },
) {
  return getData<Record<string, unknown>>({
    url: libraryUrl(labId, `/resources/${resourceId}/containers`),
    method: "POST",
    data: payload,
  })
}

export function fetchInventoryEvents(labId: string, resourceId?: string) {
  return getData<{ items: InventoryEvent[] }>({
    url: libraryUrl(labId, "/inventory/events"),
    params: { resource_id: resourceId },
  })
}

export function postInventoryOperation(
  labId: string,
  kind: "receipt" | "consumption" | "adjustment" | "count" | "disposal",
  payload: {
    container_id: string
    quantity: string
    unit: string
    idempotency_key: string
    reason?: string
  },
) {
  return getData<InventoryEvent>({
    url: libraryUrl(labId, `/inventory/operations/${kind}`),
    method: "POST",
    data: payload,
  })
}

export function transferInventory(
  labId: string,
  payload: {
    from_container_id: string
    to_container_id: string
    quantity: string
    unit: string
    idempotency_key: string
    reason?: string
  },
) {
  return getData<InventoryEvent>({
    url: libraryUrl(labId, "/inventory/transfers"),
    method: "POST",
    data: payload,
  })
}

export interface InventoryReservation {
  id: string
  resource_id: string
  container_id: string
  quantity: string
  unit: string
  status: string
  expires_at: string | null
  created_at: string
}

export function fetchInventoryReservations(labId: string) {
  return getData<{ items: InventoryReservation[] }>({
    url: libraryUrl(labId, "/inventory/reservations"),
  })
}

export function createInventoryReservation(
  labId: string,
  payload: {
    resource_id: string
    container_id: string
    quantity: string
    unit: string
    expires_at?: string
    idempotency_key: string
    reason?: string
  },
) {
  return getData<InventoryReservation>({
    url: libraryUrl(labId, "/inventory/reservations"),
    method: "POST",
    data: payload,
  })
}

export function releaseInventoryReservation(
  labId: string,
  reservationId: string,
  idempotencyKey: string,
) {
  return getData<InventoryEvent>({
    url: libraryUrl(labId, `/inventory/reservations/${reservationId}/release`),
    method: "POST",
    params: { idempotency_key: idempotencyKey },
  })
}

export function createResourceLabel(
  labId: string,
  payload: {
    target_type: "resource" | "container" | "location" | "equipment"
    target_id: string
    format: "qr" | "barcode"
  },
) {
  return getData<{
    id: string
    code: string
    target_type: string
    target_id: string
    format: string
    payload: string
  }>({
    url: libraryUrl(labId, "/labels"),
    method: "POST",
    data: payload,
  })
}

export function resolveResourceLabel(labId: string, code: string) {
  return getData<{
    id: string
    code: string
    target_type: string
    target_id: string
    format: string
  }>({
    url: libraryUrl(labId, `/labels/resolve/${encodeURIComponent(code)}`),
  })
}

export function dryRunResourceImport(
  labId: string,
  resourceTypeId: string,
  file: File,
  options: {
    name_field?: string
    code_field?: string
    field_mapping?: Record<string, string>
  } = {},
) {
  const data = new FormData()
  data.append("file", file)
  return getData<{
    rows: Array<{
      row: number
      valid: boolean
      issues: Array<{ path?: string, message: string }>
      mapped: Record<string, unknown>
    }>
    valid: number
    invalid: number
    dry_run: true
  }>({
    url: libraryUrl(labId, "/imports/dry-run"),
    method: "POST",
    params: {
      resource_type_id: resourceTypeId,
      name_field: options.name_field || "name",
      code_field: options.code_field || "code",
      field_mapping: options.field_mapping
        ? JSON.stringify(options.field_mapping)
        : undefined,
    },
    data,
  })
}

export function commitResourceImport(
  labId: string,
  resourceTypeId: string,
  file: File,
  options: {
    name_field?: string
    code_field?: string
    field_mapping?: Record<string, string>
  } = {},
) {
  const data = new FormData()
  data.append("file", file)
  return getData<{ created: number, items: ResourceItem[], dry_run: false }>({
    url: libraryUrl(labId, "/imports"),
    method: "POST",
    params: {
      resource_type_id: resourceTypeId,
      name_field: options.name_field || "name",
      code_field: options.code_field || "code",
      field_mapping: options.field_mapping
        ? JSON.stringify(options.field_mapping)
        : undefined,
    },
    data,
  })
}

export function fetchEquipmentServiceEvents(
  labId: string,
  resourceId?: string,
) {
  return getData<{ items: Array<Record<string, unknown>> }>({
    url: libraryUrl(labId, "/equipment/service-events"),
    params: { resource_id: resourceId },
  })
}

export function createEquipmentServiceEvent(
  labId: string,
  payload: {
    resource_id: string
    kind: "calibration" | "maintenance" | "fault" | "decommission"
    status: string
    starts_at: string
    ends_at?: string
    due_at?: string
    provider?: string
    notes?: string
  },
) {
  return getData<Record<string, unknown>>({
    url: libraryUrl(labId, "/equipment/service-events"),
    method: "POST",
    data: payload,
  })
}

export function fetchResourceLocations(labId: string) {
  return getData<{ items: ResourceLocation[] }>({ url: libraryUrl(labId, "/locations") })
}

export function createResourceLocation(
  labId: string,
  payload: {
    code: string
    name: string
    parent_id?: string | null
    kind?: string
    visibility?: "lab" | "restricted"
  },
) {
  return getData<ResourceLocation>({
    url: libraryUrl(labId, "/locations"),
    method: "POST",
    data: payload,
  })
}

export function fetchEquipmentBookings(
  labId: string,
  params: { resource_id?: string, starts_at?: string, ends_at?: string } = {},
) {
  return getData<{ items: EquipmentBooking[] }>({
    url: libraryUrl(labId, "/bookings"),
    params,
  })
}

export function createEquipmentBooking(
  labId: string,
  payload: {
    resource_id: string
    starts_at: string
    ends_at: string
    purpose?: string
    idempotency_key: string
  },
) {
  return getData<EquipmentBooking>({
    url: libraryUrl(labId, "/bookings"),
    method: "POST",
    data: payload,
  })
}

export function decideEquipmentBooking(
  labId: string,
  bookingId: string,
  action: "approve" | "reject" | "cancel" | "complete",
) {
  return getData<EquipmentBooking>({
    url: libraryUrl(labId, `/bookings/${bookingId}/decision`),
    method: "POST",
    data: { action },
  })
}

export function fetchResourceNotifications(labId: string) {
  return getData<{ items: ResourceNotification[] }>({
    url: libraryUrl(labId, "/notifications"),
  })
}

export function readResourceNotification(labId: string, notificationId: string) {
  return getData<{ read: boolean }>({
    url: libraryUrl(labId, `/notifications/${notificationId}/read`),
    method: "POST",
  })
}

export function searchResourceRefs(
  labId: string,
  params: {
    q?: string
    resource_type_id?: string
    resource_type?: string
    role?: "input" | "output" | "reference" | "equipment"
    limit?: number
  },
) {
  return getData<{ items: Array<{
    id: string
    label: string
    entity: "resource"
    snapshot: Record<string, unknown>
  }> }>({
    url: libraryUrl(labId, "/resolver/search"),
    params,
  })
}

export function fetchResourceAvailability(labId: string, resourceId: string) {
  return getData<{
    resource: { id: string, name: string, code: string, status: string }
    containers: Array<Record<string, unknown>>
    equipment_bookings: Array<{
      id: string
      starts_at: string
      ends_at: string
      status: string
      label: string
      available: boolean
    }>
  }>({
    url: libraryUrl(labId, `/resolver/resources/${resourceId}/availability`),
  })
}

export function fetchEquipmentSlots(
  labId: string,
  resourceId: string,
  startsAt: string,
  endsAt: string,
) {
  return getData<{
    window: { starts_at: string, ends_at: string }
    busy: Array<{ starts_at: string, ends_at: string }>
  }>({
    url: libraryUrl(labId, `/resolver/equipment/${resourceId}/slots`),
    params: { starts_at: startsAt, ends_at: endsAt },
  })
}

export function prepareResourceOutput(
  labId: string,
  payload: {
    id: string
    resource_type_id: string
    name: string
    code: string
    data: Record<string, unknown>
    visibility?: "lab" | "restricted"
    lot?: Record<string, unknown> | null
    container?: Record<string, unknown> | null
  },
) {
  return getData<{ resource_ref: Record<string, unknown> }>({
    url: libraryUrl(labId, "/resolver/prepare-output"),
    method: "POST",
    data: payload,
  })
}
