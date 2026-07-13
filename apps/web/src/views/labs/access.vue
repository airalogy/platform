<template>
  <div class="access-workspace">
    <n-tabs v-model:value="activeTab" type="line" animated @update:value="handleTabChange">
      <n-tab-pane name="grants" :tab="$t('page.labs.access.grants')">
        <div class="toolbar">
          <n-space>
            <n-select v-model:value="grantFilters.subject" clearable class="w-56" :options="subjectFilterOptions" :placeholder="$t('page.labs.access.filterSubject')" />
            <n-select v-model:value="grantFilters.resource" clearable class="w-64" :options="resourceFilterOptions" :placeholder="$t('page.labs.access.filterResource')" />
            <n-checkbox v-model:checked="grantFilters.includeRevoked" @update:checked="loadGrants">
              {{ $t("page.labs.access.includeRevoked") }}
            </n-checkbox>
          </n-space>
          <n-button v-if="canManageAny" type="primary" @click="openGrantModal()">
            <template #icon>
              <icon-ion-add-outline />
            </template>
            {{ $t("page.labs.access.addGrant") }}
          </n-button>
        </div>
        <n-data-table
          :loading="loading.grants"
          :columns="grantColumns"
          :data="filteredGrants"
          :row-key="row => row.id"
          :bordered="false"
          :single-line="false"
          :scroll-x="980"
        />
      </n-tab-pane>

      <n-tab-pane name="effective" :tab="$t('page.labs.access.effectiveAccess')">
        <div class="inspector-controls">
          <n-form-item :label="$t('page.labs.access.member')">
            <n-select v-model:value="inspector.userId" filterable :options="memberOptions" />
          </n-form-item>
          <n-form-item :label="$t('page.labs.access.project')">
            <n-select v-model:value="inspector.projectId" clearable filterable :options="projectOptions" @update:value="handleInspectorProject" />
          </n-form-item>
          <n-form-item :label="$t('page.labs.access.protocol')">
            <n-select v-model:value="inspector.protocolId" clearable filterable :disabled="!inspector.projectId" :options="inspectorProtocolOptions" />
          </n-form-item>
          <n-button type="primary" :disabled="!inspector.userId" :loading="loading.effective" @click="inspectAccess">
            <template #icon>
              <icon-tabler-shield-search />
            </template>
            {{ $t("page.labs.access.inspect") }}
          </n-button>
        </div>

        <div v-if="selectedInspectorResource && canManageSelectedResource" class="inheritance-row">
          <div>
            <strong>{{ $t("page.labs.access.inheritPermissions") }}</strong>
            <p>{{ $t("page.labs.access.inheritPermissionsHint") }}</p>
          </div>
          <n-switch :value="selectedInspectorResource.inherit_permissions !== false" :loading="loading.inheritance" @update:value="updateInheritance" />
        </div>

        <template v-if="effectiveAccess">
          <section class="effective-summary">
            <div>
              <span>{{ $t("page.labs.access.effectiveRoles") }}</span>
              <n-space class="mt-2">
                <n-tag v-for="role in effectiveAccess.role_keys" :key="role" type="info" :bordered="false">
                  {{ roleLabel(role) }}
                </n-tag>
              </n-space>
            </div>
            <div>
              <span>{{ $t("page.labs.access.capabilities") }}</span>
              <n-space class="mt-2">
                <n-tag v-for="capability in effectiveAccess.capabilities" :key="capability" size="small">
                  {{ capability }}
                </n-tag>
              </n-space>
            </div>
          </section>
          <h3 class="section-title">
            {{ $t("page.labs.access.accessSources") }}
          </h3>
          <n-data-table :columns="sourceColumns" :data="effectiveAccess.sources" :bordered="false" :single-line="false" />
        </template>
        <n-empty v-else :description="$t('page.labs.access.inspectEmpty')" class="py-16" />
      </n-tab-pane>

      <n-tab-pane v-if="canManageLab" name="audit" :tab="$t('page.labs.access.audit')">
        <n-data-table
          :loading="loading.audit"
          :columns="auditColumns"
          :data="audits"
          :row-key="row => row.id"
          :bordered="false"
          :single-line="false"
          :scroll-x="900"
        />
      </n-tab-pane>
    </n-tabs>
  </div>

  <n-modal v-model:show="grantModalVisible" preset="dialog" :title="editingGrant ? $t('page.labs.access.editGrant') : $t('page.labs.access.addGrant')" :show-icon="false" class="grant-dialog">
    <n-form ref="grantFormRef" :model="grantForm" :rules="grantRules" label-placement="top" class="mt-4">
      <div class="form-grid">
        <n-form-item :label="$t('page.labs.access.subjectType')">
          <n-radio-group v-model:value="grantForm.subjectType" :disabled="Boolean(editingGrant)" size="small">
            <n-radio-button v-for="option in subjectTypeOptions" :key="option.value" :value="option.value">
              {{ option.label }}
            </n-radio-button>
          </n-radio-group>
        </n-form-item>
        <n-form-item :label="$t('page.labs.access.subject')" path="subjectId">
          <n-select v-model:value="grantForm.subjectId" filterable :disabled="Boolean(editingGrant)" :options="grantForm.subjectType === 'user' ? memberOptions : teamOptions" />
        </n-form-item>
        <n-form-item :label="$t('page.labs.access.scopeType')">
          <n-radio-group v-model:value="grantForm.scopeType" :disabled="Boolean(editingGrant)" size="small" @update:value="resetGrantResource">
            <n-radio-button v-for="option in scopeTypeOptions" :key="option.value" :value="option.value">
              {{ option.label }}
            </n-radio-button>
          </n-radio-group>
        </n-form-item>
        <n-form-item v-if="grantForm.scopeType === 'project'" :label="$t('page.labs.access.project')" path="resourceId">
          <n-select
            v-model:value="grantForm.resourceId"
            filterable
            :disabled="Boolean(editingGrant)"
            :options="grantProjectOptions"
          />
        </n-form-item>
        <n-form-item v-if="grantForm.scopeType === 'protocol'" :label="$t('page.labs.access.project')" path="projectId">
          <n-select
            v-model:value="grantForm.projectId"
            filterable
            :disabled="Boolean(editingGrant)"
            :options="grantProjectOptions"
            @update:value="handleGrantProject"
          />
        </n-form-item>
        <n-form-item v-if="grantForm.scopeType === 'protocol'" :label="$t('page.labs.access.protocol')" path="resourceId">
          <n-select
            v-model:value="grantForm.resourceId"
            filterable
            :disabled="Boolean(editingGrant) || !grantForm.projectId"
            :options="grantProtocolOptions"
          />
        </n-form-item>
        <n-form-item :label="$t('common.role')" path="roleKey">
          <n-select v-model:value="grantForm.roleKey" :options="roleOptions" />
        </n-form-item>
        <n-form-item :label="$t('page.labs.access.expiry')">
          <n-date-picker v-model:value="grantForm.expiresAt" type="datetime" clearable class="w-full" :is-date-disabled="disablePastDate" />
        </n-form-item>
      </div>
      <n-form-item v-if="grantForm.scopeType !== 'protocol'">
        <n-checkbox v-model:checked="grantForm.inheritToChildren">
          {{ $t("page.labs.access.inheritToChildren") }}
        </n-checkbox>
      </n-form-item>
      <n-form-item :label="$t('page.labs.access.reason')">
        <n-input v-model:value="grantForm.reason" maxlength="256" show-count :placeholder="$t('page.labs.access.reasonPlaceholder')" />
      </n-form-item>
    </n-form>
    <template #action>
      <n-button @click="grantModalVisible = false">
        {{ $t("common.cancel") }}
      </n-button>
      <n-button type="primary" :loading="saving" @click="saveGrant">
        {{ $t("common.confirm") }}
      </n-button>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import type {
  AccessAudit,
  AccessGrant,
  AccessRole,
  AccessScopeType,
  AccessSource,
  AccessSubjectType,
  EffectiveAccess,
  LabTeam,
  ManageableScopes,
} from "@/service/api/access"
import type { DataTableColumns, FormInst, FormRules, SelectOption } from "naive-ui"
import { useClosableMessage } from "@/composables"
import { LabRole } from "@/enum"
import {
  fetchAccessAudit,
  fetchAccessGrants,
  fetchAccessRoles,
  fetchEffectiveAccess,
  fetchLabTeams,
  fetchManageableScopes,
  postAccessGrant,
  putAccessGrant,
  putProjectInheritance,
  putProtocolInheritance,
  revokeAccessGrant,
} from "@/service/api/access"
import { fetchLabMemberList } from "@/service/api/labs"
import { fetchProjectList } from "@/service/api/projects"
import { getProtocols } from "@/service/api/protocol"
import { $t } from "@airalogy/shared/locales"
import { NButton, NPopconfirm, NTag, NTooltip } from "naive-ui"
import { useLabInfoStore } from "./hooks/useLabsInfoStore"

defineOptions({ name: "LabAccess" })

interface ResourceItem { id: string, name: string, uid?: string, project_id?: string, inherit_permissions?: boolean }

const message = useClosableMessage()
const { labInfo, userLabRole } = useLabInfoStore()!
const canManageLab = computed(() => userLabRole.value === LabRole.OWNER || userLabRole.value === LabRole.MANAGER)
const activeTab = ref("grants")
const roles = ref<AccessRole[]>([])
const teams = ref<LabTeam[]>([])
const members = ref<Api.Lab.MemberListItem[]>([])
const projects = ref<ResourceItem[]>([])
const protocols = ref<ResourceItem[]>([])
const loadedProtocolProjectIds = new Set<string>()
const grants = ref<AccessGrant[]>([])
const audits = ref<AccessAudit[]>([])
const effectiveAccess = ref<EffectiveAccess | null>(null)
const loading = reactive({ grants: false, effective: false, audit: false, inheritance: false })
const saving = ref(false)
const grantFilters = reactive({ subject: null as string | number | null, resource: null as string | null, includeRevoked: false })
const manageableScopes = ref<ManageableScopes>({ lab: false, project_ids: [], protocol_ids: [] })
const canManageAny = computed(() => manageableScopes.value.lab || manageableScopes.value.project_ids.length > 0 || manageableScopes.value.protocol_ids.length > 0)

const memberOptions = computed<SelectOption[]>(() => members.value.map(member => ({
  label: `${member.name || member.username} (@${member.username})`,
  value: String(member.id),
})))
const teamOptions = computed<SelectOption[]>(() => teams.value.map(team => ({ label: team.name, value: team.id })))
const projectOptions = computed<SelectOption[]>(() => projects.value.map(project => ({ label: `${project.name} (${project.uid})`, value: project.id })))
const allProtocolOptions = computed<SelectOption[]>(() => protocols.value.map(protocol => ({ label: protocol.name, value: protocol.id })))
const grantProjectOptions = computed(() => projectOptions.value.filter(option => manageableScopes.value.project_ids.includes(String(option.value))))
const roleOptions = computed<SelectOption[]>(() => roles.value.filter(role => role.grantable).map(role => ({ label: role.label, value: role.key })))
const subjectTypeOptions = computed(() => [
  { label: $t("page.labs.access.user"), value: "user" },
  { label: $t("page.labs.access.team"), value: "team" },
])
const scopeTypeOptions = computed(() => [
  manageableScopes.value.lab ? { label: "Lab", value: "lab" } : null,
  grantProjectOptions.value.length ? { label: $t("page.labs.access.project"), value: "project" } : null,
  manageableScopes.value.protocol_ids.length ? { label: $t("page.labs.access.protocol"), value: "protocol" } : null,
].filter(Boolean) as Array<{ label: string, value: AccessScopeType }>)

async function loadReferenceData() {
  if (!labInfo.value?.id)
    return
  const labId = String(labInfo.value.id)
  const [roleResult, teamResult, memberResult, projectResult, scopesResult] = await Promise.all([
    fetchAccessRoles(),
    fetchLabTeams(labId),
    fetchLabMemberList(labId, { page: 1, pageSize: 1000 }),
    fetchProjectList({ labId, page: 1, pageSize: 1000 }),
    fetchManageableScopes(labId),
  ])
  roles.value = roleResult.data?.roles || []
  teams.value = teamResult.data?.teams || []
  members.value = memberResult?.users || []
  projects.value = (projectResult?.projects || []) as ResourceItem[]
  manageableScopes.value = scopesResult.data || { lab: false, project_ids: [], protocol_ids: [] }
}

async function loadProtocols(projectId: string | null) {
  if (!projectId || loadedProtocolProjectIds.has(projectId))
    return
  const { data } = await getProtocols({ projectId, page: 1, pageSize: 1000 })
  const loaded = ((data as any)?.protocols || []) as ResourceItem[]
  loadedProtocolProjectIds.add(projectId)
  const existingIds = new Set(protocols.value.map(protocol => protocol.id))
  protocols.value.push(...loaded.filter(protocol => !existingIds.has(protocol.id)))
}

async function loadGrants() {
  if (!labInfo.value?.id || !canManageAny.value)
    return
  loading.grants = true
  try {
    const { data } = await fetchAccessGrants(String(labInfo.value.id), { includeRevoked: grantFilters.includeRevoked })
    grants.value = data?.grants || []
  }
  finally {
    loading.grants = false
  }
}

const subjectFilterOptions = computed<SelectOption[]>(() => [
  ...memberOptions.value.map(option => ({ ...option, value: `user:${option.value}` })),
  ...teamOptions.value.map(option => ({ ...option, value: `team:${option.value}` })),
])
const resourceFilterOptions = computed<SelectOption[]>(() => [
  { label: labInfo.value?.name || "Lab", value: `lab:${labInfo.value?.id}` },
  ...projectOptions.value.map(option => ({ ...option, value: `project:${option.value}` })),
  ...allProtocolOptions.value.map(option => ({ ...option, value: `protocol:${option.value}` })),
])
const filteredGrants = computed(() => grants.value.filter((grant) => {
  const subject = grant.subject_type === "user" ? `user:${grant.user_id}` : `team:${grant.group_id}`
  const resourceId = grant.scope_type === "lab" ? grant.lab_id : grant.scope_type === "project" ? grant.project_id : grant.protocol_id
  const resource = `${grant.scope_type}:${resourceId}`
  return (!grantFilters.subject || subject === grantFilters.subject) && (!grantFilters.resource || resource === grantFilters.resource)
}))

function roleLabel(key: string) {
  return roles.value.find(role => role.key === key)?.label || key
}
function memberLabel(id: string | null) {
  const member = members.value.find(item => String(item.id) === id)
  return member ? member.name || member.username : id || "-"
}
function teamLabel(id: number | null) {
  return teams.value.find(team => team.id === id)?.name || String(id || "-")
}
function subjectLabel(grant: AccessGrant) {
  return grant.subject_type === "user" ? memberLabel(grant.user_id) : teamLabel(grant.group_id)
}
function resourceLabel(scopeType: AccessScopeType, scopeId: string | number | null) {
  if (scopeType === "lab")
    return labInfo.value?.name || "Lab"
  if (scopeType === "project")
    return projects.value.find(item => item.id === scopeId)?.name || String(scopeId || "-")
  return protocols.value.find(item => item.id === scopeId)?.name || String(scopeId || "-")
}
function grantResourceId(grant: AccessGrant) {
  return grant.scope_type === "lab" ? grant.lab_id : grant.scope_type === "project" ? grant.project_id : grant.protocol_id
}
function canManageGrant(grant: AccessGrant) {
  if (grant.scope_type === "lab")
    return manageableScopes.value.lab
  if (grant.scope_type === "project")
    return manageableScopes.value.project_ids.includes(String(grant.project_id))
  if (grant.scope_type === "protocol")
    return manageableScopes.value.protocol_ids.includes(String(grant.protocol_id))
  return false
}
function formatDate(value: string | null) {
  return value ? new Date(value).toLocaleString() : $t("page.labs.access.never")
}

const grantColumns = computed<DataTableColumns<AccessGrant>>(() => [
  { title: $t("page.labs.access.subject"), key: "subject", width: 180, render: row => h("div", [h("strong", subjectLabel(row)), h("div", { class: "text-xs text-gray-500" }, row.subject_type)]) },
  { title: $t("page.labs.access.resource"), key: "resource", width: 210, render: row => h("div", [h("strong", resourceLabel(row.scope_type, grantResourceId(row))), h("div", { class: "text-xs text-gray-500" }, row.scope_type)]) },
  { title: $t("common.role"), key: "role_key", width: 170, render: row => h(NTag, { bordered: false, type: "info" }, { default: () => roleLabel(row.role_key) }) },
  { title: $t("page.labs.access.inheritance"), key: "inherit_to_children", width: 120, render: row => row.inherit_to_children ? $t("page.labs.access.yes") : $t("page.labs.access.no") },
  { title: $t("page.labs.access.expiry"), key: "expires_at", width: 190, render: row => formatDate(row.expires_at) },
  { title: $t("common.status"), key: "status", width: 100, render: row => h(NTag, { bordered: false, type: row.revoked_at ? "error" : row.expires_at && new Date(row.expires_at) < new Date() ? "warning" : "success" }, { default: () => row.revoked_at ? $t("page.labs.access.revoked") : row.expires_at && new Date(row.expires_at) < new Date() ? $t("page.labs.access.expired") : $t("page.labs.access.active") }) },
  { title: "", key: "actions", fixed: "right", width: 90, render: row => !row.revoked_at && canManageGrant(row)
    ? h("div", { class: "flex gap-1" }, [
      h(NTooltip, null, {
        trigger: () => h(NButton, { quaternary: true, circle: true, size: "small", onClick: () => openGrantModal(row) }, { default: () => h("span", { class: "i-ion-pencil-outline" }) }),
        default: () => $t("common.edit"),
      }),
      h(NPopconfirm, { onPositiveClick: () => revokeGrant(row) }, { trigger: () => h(NButton, { quaternary: true, circle: true, type: "error", size: "small" }, { default: () => h("span", { class: "i-tabler-shield-x" }) }), default: () => $t("page.labs.access.revokeConfirm") }),
    ])
    : null },
])

const grantModalVisible = ref(false)
const editingGrant = ref<AccessGrant | null>(null)
const grantFormRef = ref<FormInst | null>(null)
const grantForm = reactive({
  subjectType: "user" as AccessSubjectType,
  subjectId: null as string | number | null,
  scopeType: "lab" as AccessScopeType,
  projectId: null as string | null,
  resourceId: null as string | null,
  roleKey: "viewer",
  inheritToChildren: true,
  expiresAt: null as number | null,
  reason: "",
})
const grantProtocolOptions = computed(() => allProtocolOptions.value.filter((option) => {
  const protocol = protocols.value.find(item => item.id === option.value)
  return protocol?.project_id === grantForm.projectId
    && manageableScopes.value.protocol_ids.includes(String(option.value))
}))
const grantRules: FormRules = {
  subjectId: { required: true, message: $t("page.labs.access.subjectRequired"), trigger: "change" },
  projectId: { validator: () => grantForm.scopeType !== "protocol" || Boolean(grantForm.projectId), message: $t("page.labs.access.resourceRequired"), trigger: "change" },
  resourceId: { validator: () => grantForm.scopeType === "lab" || Boolean(grantForm.resourceId), message: $t("page.labs.access.resourceRequired"), trigger: "change" },
  roleKey: { required: true, message: $t("page.labs.access.roleRequired"), trigger: "change" },
}

function openGrantModal(grant?: AccessGrant) {
  editingGrant.value = grant || null
  const defaultScope = scopeTypeOptions.value[0]?.value || "project"
  Object.assign(grantForm, grant
    ? {
        subjectType: grant.subject_type,
        subjectId: grant.user_id || grant.group_id,
        scopeType: grant.scope_type,
        projectId: grant.scope_type === "protocol" ? grant.project_id : null,
        resourceId: grant.scope_type === "project" ? grant.project_id : grant.scope_type === "protocol" ? grant.protocol_id : null,
        roleKey: grant.role_key,
        inheritToChildren: grant.inherit_to_children,
        expiresAt: grant.expires_at ? new Date(grant.expires_at).getTime() : null,
        reason: grant.reason,
      }
    : {
        subjectType: "user",
        subjectId: null,
        scopeType: defaultScope,
        projectId: null,
        resourceId: null,
        roleKey: "viewer",
        inheritToChildren: true,
        expiresAt: null,
        reason: "",
      })
  grantModalVisible.value = true
}
function resetGrantResource() {
  grantForm.projectId = null
  grantForm.resourceId = null
}
async function handleGrantProject(projectId: string | null) {
  grantForm.resourceId = null
  await loadProtocols(projectId)
}
function disablePastDate(timestamp: number) {
  return timestamp < new Date().setHours(0, 0, 0, 0)
}
async function saveGrant() {
  await grantFormRef.value?.validate()
  if (!labInfo.value?.id)
    return
  saving.value = true
  try {
    if (editingGrant.value) {
      await putAccessGrant(editingGrant.value.id, {
        roleKey: grantForm.roleKey,
        inheritToChildren: grantForm.inheritToChildren,
        expiresAt: grantForm.expiresAt ? new Date(grantForm.expiresAt).toISOString() : null,
        clearExpiry: !grantForm.expiresAt,
        reason: grantForm.reason,
      })
    }
    else {
      await postAccessGrant({
        labId: String(labInfo.value.id),
        subjectType: grantForm.subjectType,
        userId: grantForm.subjectType === "user" ? String(grantForm.subjectId) : null,
        groupId: grantForm.subjectType === "team" ? Number(grantForm.subjectId) : null,
        scopeType: grantForm.scopeType,
        projectId: grantForm.scopeType === "project" ? grantForm.resourceId : grantForm.scopeType === "protocol" ? grantForm.projectId : null,
        protocolId: grantForm.scopeType === "protocol" ? grantForm.resourceId : null,
        roleKey: grantForm.roleKey,
        inheritToChildren: grantForm.inheritToChildren,
        expiresAt: grantForm.expiresAt ? new Date(grantForm.expiresAt).toISOString() : null,
        reason: grantForm.reason,
      })
    }
    grantModalVisible.value = false
    message.success($t("page.labs.access.saved"))
    await loadGrants()
  }
  finally {
    saving.value = false
  }
}
async function revokeGrant(grant: AccessGrant) {
  await revokeAccessGrant(grant.id, $t("page.labs.access.revokedFromWorkspace"))
  message.success($t("page.labs.access.saved"))
  await loadGrants()
}

const inspector = reactive({ userId: null as string | null, projectId: null as string | null, protocolId: null as string | null })
const inspectorProtocolOptions = computed(() => allProtocolOptions.value.filter(option => protocols.value.find(protocol => protocol.id === option.value)?.project_id === inspector.projectId))
const selectedInspectorResource = computed(() => inspector.protocolId ? protocols.value.find(item => item.id === inspector.protocolId) : inspector.projectId ? projects.value.find(item => item.id === inspector.projectId) : null)
const canManageSelectedResource = computed(() => inspector.protocolId
  ? manageableScopes.value.protocol_ids.includes(inspector.protocolId)
  : Boolean(inspector.projectId && manageableScopes.value.project_ids.includes(inspector.projectId)))
async function handleInspectorProject(projectId: string | null) {
  inspector.protocolId = null
  effectiveAccess.value = null
  await loadProtocols(projectId)
}
async function inspectAccess() {
  if (!labInfo.value?.id || !inspector.userId)
    return
  loading.effective = true
  try {
    const { data } = await fetchEffectiveAccess(String(labInfo.value.id), {
      userId: inspector.userId,
      projectId: inspector.projectId,
      protocolId: inspector.protocolId,
    })
    effectiveAccess.value = data || null
  }
  finally {
    loading.effective = false
  }
}
async function updateInheritance(value: boolean) {
  const resource = selectedInspectorResource.value
  if (!resource)
    return
  loading.inheritance = true
  try {
    if (inspector.protocolId)
      await putProtocolInheritance(resource.id, value)
    else await putProjectInheritance(resource.id, value)
    resource.inherit_permissions = value
    message.success($t("page.labs.access.saved"))
    if (inspector.userId)
      await inspectAccess()
  }
  finally {
    loading.inheritance = false
  }
}
const sourceColumns = computed<DataTableColumns<AccessSource>>(() => [
  { title: $t("page.labs.access.source"), key: "source_type" },
  { title: $t("common.role"), key: "role_key", render: row => roleLabel(row.role_key) },
  { title: $t("page.labs.access.scopeType"), key: "scope_type" },
  { title: $t("page.labs.access.inherited"), key: "inherited", render: row => row.inherited ? $t("page.labs.access.yes") : $t("page.labs.access.no") },
  { title: $t("page.labs.access.subject"), key: "subject_id", render: row => row.subject_type === "team" ? teamLabel(Number(row.subject_id)) : memberLabel(row.subject_id) },
])

async function loadAudit() {
  if (!labInfo.value?.id || !canManageLab.value)
    return
  loading.audit = true
  try {
    const { data } = await fetchAccessAudit(String(labInfo.value.id))
    audits.value = data?.audits || []
  }
  finally {
    loading.audit = false
  }
}
const auditColumns = computed<DataTableColumns<AccessAudit>>(() => [
  { title: $t("page.labs.access.time"), key: "created_at", width: 190, render: row => formatDate(row.created_at) },
  { title: $t("page.labs.access.action"), key: "action", width: 110, render: row => h(NTag, { bordered: false, type: row.action === "revoked" ? "error" : row.action === "updated" ? "warning" : "success" }, { default: () => row.action }) },
  { title: $t("page.labs.access.actor"), key: "actor_user_id", width: 180, render: row => memberLabel(row.actor_user_id) },
  { title: $t("page.labs.access.subject"), key: "subject", width: 180, render: row => row.after_state ? subjectLabel(row.after_state) : row.before_state ? subjectLabel(row.before_state) : "-" },
  { title: $t("common.role"), key: "role", width: 160, render: row => roleLabel(row.after_state?.role_key || row.before_state?.role_key || "") },
  { title: $t("page.labs.access.reason"), key: "reason" },
])

async function handleTabChange(tab: string) {
  if (tab === "audit" && !audits.value.length)
    await loadAudit()
}

watch(() => labInfo.value?.id, async (id) => {
  if (!id)
    return
  await loadReferenceData()
  if (!canManageAny.value)
    activeTab.value = "effective"
  await loadGrants()
}, { immediate: true })
</script>

<style scoped>
.access-workspace { min-height: 540px; }
.toolbar { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 14px; }
.inspector-controls { display: grid; grid-template-columns: minmax(180px, 1fr) minmax(180px, 1fr) minmax(180px, 1fr) auto; align-items: end; gap: 12px; margin-bottom: 18px; }
.inspector-controls :deep(.n-form-item) { margin-bottom: 0; }
.inheritance-row { display: flex; align-items: center; justify-content: space-between; gap: 20px; border-block: 1px solid #e5e7eb; padding: 12px 0; }
.inheritance-row p { margin: 3px 0 0; color: #6b7280; font-size: 12px; }
.effective-summary { display: grid; grid-template-columns: minmax(200px, .7fr) minmax(0, 1.3fr); gap: 28px; padding: 20px 0; }
.effective-summary > div > span { color: #6b7280; font-size: 12px; font-weight: 600; text-transform: uppercase; }
.section-title { margin: 8px 0 12px; font-size: 15px; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0 16px; }
:global(.grant-dialog) { width: min(720px, calc(100vw - 32px)); }
@media (max-width: 900px) {
  .inspector-controls { grid-template-columns: 1fr 1fr; }
}
@media (max-width: 640px) {
  .toolbar { align-items: stretch; flex-direction: column; }
  .inspector-controls, .effective-summary, .form-grid { grid-template-columns: 1fr; }
}
</style>
