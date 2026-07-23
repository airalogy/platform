import { request } from "../request"

export type AccessScopeType = "lab" | "project" | "protocol" | "resource_type" | "resource" | "location"
export type AccessSubjectType = "user" | "org_unit"
export type OrganizationalUnitMembershipRole = "manager" | "member"
export type OrganizationalUnitType = "department" | "research_group" | "core_facility" | "project_team" | "committee" | "other"

export interface AccessRole {
  key: string
  label: string
  capabilities: string[]
  grantable: boolean
}

export interface OrganizationalUnitMember {
  id: string
  username: string
  name: string
  membership_role: OrganizationalUnitMembershipRole
}

export interface LabOrganizationalUnit {
  id: number
  lab_id: string
  parent_unit_id: number | null
  parent_group_id: number | null
  unit_type: OrganizationalUnitType
  uid: string
  name: string
  description: string
  users_count: number
  members: OrganizationalUnitMember[]
}

export interface AccessGrant {
  id: string
  lab_id: string
  subject_type: AccessSubjectType | "team"
  user_id: string | null
  org_unit_id: number | null
  group_id: number | null
  scope_type: AccessScopeType
  project_id: string | null
  protocol_id: string | null
  resource_type_id: string | null
  resource_id: string | null
  location_id: string | null
  role_key: string
  inherit_to_children: boolean
  expires_at: string | null
  revoked_at: string | null
  reason: string
  created_by_user_id: string
  created_at: string
  updated_at: string
}

export interface AccessSource {
  source_type: string
  role_key: string
  scope_type: AccessScopeType
  scope_id: string
  inherited: boolean
  grant_id: string | null
  subject_type: AccessSubjectType | "team" | null
  subject_id: string | null
}

export interface EffectiveAccess {
  capabilities: string[]
  role_keys: string[]
  sources: AccessSource[]
}

export interface ManageableScopes {
  lab: boolean
  project_ids: string[]
  protocol_ids: string[]
  resource_type_ids: string[]
  resource_ids: string[]
  location_ids: string[]
}

export interface AccessAudit {
  id: string
  grant_id: string
  actor_user_id: string
  action: "created" | "updated" | "revoked"
  before_state: AccessGrant | null
  after_state: AccessGrant | null
  reason: string
  created_at: string
}

export interface GrantPayload {
  labId: string
  subjectType: AccessSubjectType
  userId?: string | null
  orgUnitId?: number | null
  groupId?: number | null
  scopeType: AccessScopeType
  projectId?: string | null
  protocolId?: string | null
  resourceTypeId?: string | null
  resourceId?: string | null
  locationId?: string | null
  roleKey: string
  inheritToChildren: boolean
  expiresAt?: string | null
  reason: string
}

function grantData(payload: GrantPayload) {
  return {
    lab_id: payload.labId,
    subject_type: payload.subjectType,
    user_id: payload.subjectType === "user" ? payload.userId : null,
    org_unit_id: payload.subjectType === "org_unit" ? payload.orgUnitId || payload.groupId : null,
    scope_type: payload.scopeType,
    project_id: payload.scopeType === "project" || payload.scopeType === "protocol" ? payload.projectId : null,
    protocol_id: payload.scopeType === "protocol" ? payload.protocolId : null,
    resource_type_id: payload.scopeType === "resource_type" ? payload.resourceTypeId : null,
    resource_id: payload.scopeType === "resource" ? payload.resourceId : null,
    location_id: payload.scopeType === "location" ? payload.locationId : null,
    role_key: payload.roleKey,
    inherit_to_children: payload.inheritToChildren,
    expires_at: payload.expiresAt || null,
    reason: payload.reason,
  }
}

export async function fetchAccessRoles() {
  return request<{ roles: AccessRole[] }>({ url: "/access/roles" })
}

export async function fetchLabOrganizationalUnits(labId: string) {
  return request<{ organizational_units: LabOrganizationalUnit[] }>({ url: `/access/labs/${labId}/organizational-units` })
}

export async function postOrganizationalUnit(payload: {
  labId: string
  uid: string
  name: string
  description: string
  unitType: OrganizationalUnitType
  parentUnitId?: number | null
}) {
  return request<LabOrganizationalUnit>({
    url: "/access/organizational-units",
    method: "POST",
    data: {
      lab_id: payload.labId,
      uid: payload.uid,
      name: payload.name,
      description: payload.description,
      unit_type: payload.unitType,
      parent_unit_id: payload.parentUnitId || null,
    },
  })
}

export async function putOrganizationalUnit(unitId: number, payload: {
  name?: string
  description?: string
  unitType?: OrganizationalUnitType
  parentUnitId?: number | null
  updateParent?: boolean
}) {
  return request<LabOrganizationalUnit>({
    url: `/access/organizational-units/${unitId}`,
    method: "PUT",
    data: {
      name: payload.name,
      description: payload.description,
      unit_type: payload.unitType,
      parent_unit_id: payload.parentUnitId,
      update_parent: payload.updateParent || false,
    },
  })
}

export async function deleteOrganizationalUnit(unitId: number) {
  return request({ url: `/access/organizational-units/${unitId}`, method: "DELETE" })
}

export async function putOrganizationalUnitMember(unitId: number, payload: {
  userId: string
  membershipRole: OrganizationalUnitMembershipRole
}) {
  return request({
    url: `/access/organizational-units/${unitId}/members`,
    method: "POST",
    data: { user_id: payload.userId, membership_role: payload.membershipRole },
  })
}

export async function deleteOrganizationalUnitMember(unitId: number, userId: string) {
  return request({
    url: `/access/organizational-units/${unitId}/members/${userId}`,
    method: "DELETE",
  })
}

export async function fetchAccessGrants(labId: string, filters: Partial<{
  userId: string
  orgUnitId: number
  projectId: string
  protocolId: string
  resourceTypeId: string
  resourceId: string
  locationId: string
  includeRevoked: boolean
}> = {}) {
  return request<{ grants: AccessGrant[] }>({
    url: `/access/labs/${labId}/grants`,
    params: {
      user_id: filters.userId,
      org_unit_id: filters.orgUnitId,
      project_id: filters.projectId,
      protocol_id: filters.protocolId,
      resource_type_id: filters.resourceTypeId,
      resource_id: filters.resourceId,
      location_id: filters.locationId,
      include_revoked: filters.includeRevoked,
    },
  })
}

export async function fetchManageableScopes(labId: string) {
  return request<ManageableScopes>({
    url: `/access/labs/${labId}/manageable-scopes`,
  })
}

export async function postAccessGrant(payload: GrantPayload) {
  return request<AccessGrant>({
    url: "/access/grants",
    method: "POST",
    data: grantData(payload),
  })
}

export async function putAccessGrant(grantId: string, payload: {
  roleKey?: string
  inheritToChildren?: boolean
  expiresAt?: string | null
  clearExpiry?: boolean
  reason: string
}) {
  return request<AccessGrant>({
    url: `/access/grants/${grantId}`,
    method: "PUT",
    data: {
      role_key: payload.roleKey,
      inherit_to_children: payload.inheritToChildren,
      expires_at: payload.expiresAt,
      clear_expiry: payload.clearExpiry || false,
      reason: payload.reason,
    },
  })
}

export async function revokeAccessGrant(grantId: string, reason: string) {
  return request<AccessGrant>({
    url: `/access/grants/${grantId}/revoke`,
    method: "POST",
    data: { reason },
  })
}

export async function fetchEffectiveAccess(labId: string, payload: {
  userId: string
  projectId?: string | null
  protocolId?: string | null
  resourceTypeId?: string | null
  resourceId?: string | null
  locationId?: string | null
}) {
  return request<EffectiveAccess>({
    url: `/access/labs/${labId}/effective`,
    params: {
      user_id: payload.userId,
      project_id: payload.projectId,
      protocol_id: payload.protocolId,
      resource_type_id: payload.resourceTypeId,
      resource_id: payload.resourceId,
      location_id: payload.locationId,
    },
  })
}

export async function fetchAccessAudit(labId: string, page = 1, pageSize = 50) {
  return request<{ audits: AccessAudit[], total_count: number }>({
    url: `/access/labs/${labId}/audit`,
    params: { page, page_size: pageSize },
  })
}

export async function putProjectInheritance(projectId: string, inheritPermissions: boolean) {
  return request({
    url: `/access/projects/${projectId}/inheritance`,
    method: "PUT",
    data: { inherit_permissions: inheritPermissions },
  })
}

export async function putProtocolInheritance(protocolId: string, inheritPermissions: boolean) {
  return request({
    url: `/access/protocols/${protocolId}/inheritance`,
    method: "PUT",
    data: { inherit_permissions: inheritPermissions },
  })
}
