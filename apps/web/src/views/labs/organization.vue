<template>
  <div class="organization-workspace">
    <aside class="organization-tree-pane">
      <div class="pane-header">
        <div>
          <h3>{{ $t("page.labs.access.organizationalUnits") }}</h3>
          <span>{{ $t("page.labs.access.unitCount", { count: organizationalUnits.length }) }}</span>
        </div>
        <n-tooltip v-if="canCreateUnit">
          <template #trigger>
            <n-button quaternary circle type="primary" @click="openUnitModal()">
              <template #icon>
                <icon-ion-add-outline />
              </template>
            </n-button>
          </template>
          {{ $t("page.labs.access.createUnit") }}
        </n-tooltip>
      </div>
      <n-spin :show="loading">
        <n-tree
          v-if="treeData.length"
          block-line
          default-expand-all
          :data="treeData"
          :selected-keys="selectedUnitId ? [selectedUnitId] : []"
          @update:selected-keys="selectUnit"
        />
        <n-empty v-else :description="$t('page.labs.access.noUnits')" class="py-12" />
      </n-spin>
    </aside>

    <section class="organization-detail-pane">
      <template v-if="selectedUnit">
        <header class="detail-header">
          <div class="min-w-0">
            <div class="flex flex-wrap items-center gap-2">
              <h3 class="truncate">
                {{ selectedUnit.name }}
              </h3>
              <n-tag size="small" :bordered="false">
                {{ selectedUnit.uid }}
              </n-tag>
              <n-tag size="small" :bordered="false" type="info">
                {{ unitTypeLabel(selectedUnit.unit_type) }}
              </n-tag>
            </div>
            <p>{{ selectedUnit.description || $t("page.labs.access.noDescription") }}</p>
          </div>
          <n-space v-if="canManageSelectedUnit">
            <n-tooltip>
              <template #trigger>
                <n-button quaternary circle @click="openUnitModal(selectedUnit)">
                  <template #icon>
                    <icon-ion-pencil-outline />
                  </template>
                </n-button>
              </template>
              {{ $t("common.edit") }}
            </n-tooltip>
            <n-popconfirm @positive-click="removeSelectedUnit">
              <template #trigger>
                <n-button quaternary circle type="error">
                  <template #icon>
                    <icon-ion-trash-outline />
                  </template>
                </n-button>
              </template>
              {{ $t("page.labs.access.deleteUnitConfirm") }}
            </n-popconfirm>
          </n-space>
        </header>

        <div class="member-toolbar">
          <div>
            <strong>{{ $t("page.labs.members") }}</strong>
            <span>{{ selectedUnit.members.length }}</span>
          </div>
          <n-button v-if="canManageSelectedUnit" type="primary" size="small" @click="openMemberModal">
            <template #icon>
              <icon-local-user-plus />
            </template>
            {{ $t("common.addMember") }}
          </n-button>
        </div>

        <n-data-table
          :columns="memberColumns"
          :data="selectedUnit.members"
          :row-key="row => row.id"
          :bordered="false"
          :single-line="false"
        />
      </template>
      <n-empty v-else :description="$t('page.labs.access.selectUnit')" class="m-auto" />
    </section>
  </div>

  <n-modal v-model:show="unitModalVisible" preset="dialog" :title="editingUnit ? $t('page.labs.access.editUnit') : $t('page.labs.access.createUnit')" :show-icon="false">
    <n-form ref="unitFormRef" :model="unitForm" :rules="unitRules" label-placement="top" class="mt-4">
      <n-form-item :label="$t('common.name')" path="name">
        <n-input v-model:value="unitForm.name" maxlength="64" show-count />
      </n-form-item>
      <n-form-item v-if="!editingUnit" :label="$t('page.labs.access.unitId')" path="uid">
        <n-input v-model:value="unitForm.uid" placeholder="molecular_biology" />
      </n-form-item>
      <n-form-item :label="$t('page.labs.access.unitType')" path="unitType">
        <n-select v-model:value="unitForm.unitType" :options="unitTypeOptions" />
      </n-form-item>
      <n-form-item v-if="!editingUnit || canManageLab" :label="$t('page.labs.access.parentUnit')">
        <n-tree-select
          v-model:value="unitForm.parentUnitId"
          clearable
          :options="parentOptions"
          :placeholder="$t('page.labs.access.rootUnit')"
        />
      </n-form-item>
      <n-form-item :label="$t('common.description')">
        <n-input v-model:value="unitForm.description" type="textarea" maxlength="256" show-count />
      </n-form-item>
    </n-form>
    <template #action>
      <n-button @click="unitModalVisible = false">
        {{ $t("common.cancel") }}
      </n-button>
      <n-button type="primary" :loading="saving" @click="saveUnit">
        {{ $t("common.confirm") }}
      </n-button>
    </template>
  </n-modal>

  <n-modal v-model:show="memberModalVisible" preset="dialog" :title="$t('common.addMember')" :show-icon="false">
    <n-form label-placement="top" class="mt-4">
      <n-form-item :label="$t('page.labs.access.member')">
        <n-select v-model:value="memberForm.userId" filterable :options="availableMemberOptions" />
      </n-form-item>
      <n-form-item :label="$t('common.role')">
        <n-select v-model:value="memberForm.membershipRole" :options="membershipRoleOptions" />
      </n-form-item>
    </n-form>
    <template #action>
      <n-button @click="memberModalVisible = false">
        {{ $t("common.cancel") }}
      </n-button>
      <n-button type="primary" :loading="saving" :disabled="!memberForm.userId" @click="saveMember">
        {{ $t("common.confirm") }}
      </n-button>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import type { LabOrganizationalUnit, OrganizationalUnitMember, OrganizationalUnitMembershipRole, OrganizationalUnitType } from "@/service/api/access"
import type { DataTableColumns, FormInst, FormRules, TreeOption } from "naive-ui"
import { useClosableMessage } from "@/composables"
import { LabRole } from "@/enum"
import {
  deleteOrganizationalUnit,
  deleteOrganizationalUnitMember,
  fetchLabOrganizationalUnits,
  postOrganizationalUnit,
  putOrganizationalUnit,
  putOrganizationalUnitMember,
} from "@/service/api/access"
import { fetchLabMemberList } from "@/service/api/labs"
import { useAuthStore } from "@/store/modules/auth"
import { $t } from "@airalogy/shared/locales"
import { NButton, NPopconfirm, NSelect, NTag } from "naive-ui"
import { useLabInfoStore } from "./hooks/useLabsInfoStore"

defineOptions({ name: "LabOrganizationalUnits" })

const message = useClosableMessage()
const { labInfo, userLabRole } = useLabInfoStore()!
const { userInfo } = useAuthStore()
const canManageLab = computed(() => userLabRole.value === LabRole.OWNER || userLabRole.value === LabRole.MANAGER)
const loading = ref(false)
const saving = ref(false)
const organizationalUnits = ref<LabOrganizationalUnit[]>([])
const labMembers = ref<Api.Lab.MemberListItem[]>([])
const selectedUnitId = ref<number | null>(null)
const selectedUnit = computed(() => organizationalUnits.value.find(unit => unit.id === selectedUnitId.value) || null)
const editingUnit = ref<LabOrganizationalUnit | null>(null)
const membershipRoleOptions = computed(() => [
  { label: $t("page.labs.access.unitManager"), value: "manager" },
  { label: $t("page.labs.access.unitMember"), value: "member" },
])
const unitTypeOptions = computed(() => ([
  "department",
  "research_group",
  "core_facility",
  "project_team",
  "committee",
  "other",
] as OrganizationalUnitType[]).map(value => ({ label: unitTypeLabel(value), value })))

function unitTypeLabel(type: OrganizationalUnitType) {
  return $t(`page.labs.access.unitTypes.${type}`)
}

function canManageUnit(unit: LabOrganizationalUnit | null) {
  if (!unit)
    return false
  if (canManageLab.value)
    return true
  const byId = new Map(organizationalUnits.value.map(item => [item.id, item]))
  const visited = new Set<number>()
  let current: LabOrganizationalUnit | undefined = unit
  while (current && !visited.has(current.id)) {
    visited.add(current.id)
    if (current.members.some(member => member.id === String(userInfo.id) && member.membership_role === "manager"))
      return true
    current = current.parent_unit_id ? byId.get(current.parent_unit_id) : undefined
  }
  return false
}

const canManageSelectedUnit = computed(() => canManageUnit(selectedUnit.value))
const manageableUnits = computed(() => organizationalUnits.value.filter(unit => canManageUnit(unit)))
const canCreateUnit = computed(() => canManageLab.value || manageableUnits.value.length > 0)

function buildTree(parentId: number | null = null, excludedId?: number): TreeOption[] {
  return organizationalUnits.value
    .filter(unit => unit.parent_unit_id === parentId && unit.id !== excludedId)
    .map(unit => ({
      key: unit.id,
      label: `${unit.name} · ${unitTypeLabel(unit.unit_type)}`,
      children: buildTree(unit.id, excludedId),
    }))
}

const treeData = computed(() => buildTree())
const parentOptions = computed(() => canManageLab.value
  ? buildTree(null, editingUnit.value?.id)
  : manageableUnits.value
    .filter(unit => unit.id !== editingUnit.value?.id)
    .map(unit => ({ key: unit.id, label: unit.name })))

async function load() {
  if (!labInfo.value?.id)
    return
  loading.value = true
  try {
    const [unitResult, memberResult] = await Promise.all([
      fetchLabOrganizationalUnits(String(labInfo.value.id)),
      fetchLabMemberList(String(labInfo.value.id), { page: 1, pageSize: 1000 }),
    ])
    organizationalUnits.value = unitResult.data?.organizational_units || []
    labMembers.value = memberResult?.users || []
    if (!selectedUnitId.value || !organizationalUnits.value.some(unit => unit.id === selectedUnitId.value)) {
      selectedUnitId.value = organizationalUnits.value[0]?.id || null
    }
  }
  finally {
    loading.value = false
  }
}

function selectUnit(keys: Array<string | number>) {
  selectedUnitId.value = Number(keys[0]) || null
}

const memberColumns = computed<DataTableColumns<OrganizationalUnitMember>>(() => [
  {
    title: $t("common.name"),
    key: "name",
    render: row => h("div", [h("strong", row.name || row.username), h("div", { class: "text-xs text-gray-500" }, `@${row.username}`)]),
  },
  {
    title: $t("common.role"),
    key: "membership_role",
    width: 180,
    render: row => canManageSelectedUnit.value
      ? h(NSelect, {
        value: row.membership_role,
        options: membershipRoleOptions.value,
        size: "small",
        onUpdateValue: (value: OrganizationalUnitMembershipRole) => updateMemberRole(row, value),
      })
      : h(NTag, { size: "small", bordered: false }, { default: () => roleLabel(row.membership_role) }),
  },
  {
    title: "",
    key: "actions",
    width: 56,
    render: row => canManageSelectedUnit.value
      ? h(NPopconfirm, { onPositiveClick: () => removeMember(row) }, {
        trigger: () => h(NButton, { quaternary: true, circle: true, type: "error", size: "small" }, { default: () => h("span", { class: "i-ion-trash-outline" }) }),
        default: () => $t("page.labs.access.removeUnitMemberConfirm"),
      })
      : null,
  },
])

const unitModalVisible = ref(false)
const unitFormRef = ref<FormInst | null>(null)
const unitForm = reactive({
  name: "",
  uid: "",
  description: "",
  unitType: "research_group" as OrganizationalUnitType,
  parentUnitId: null as number | null,
})
const unitRules: FormRules = {
  name: { required: true, message: $t("page.labs.access.unitNameRequired"), trigger: ["input", "blur"] },
  uid: { required: true, pattern: /^[a-z][a-z0-9_]{2,31}$/, message: $t("page.labs.access.unitIdHint"), trigger: ["input", "blur"] },
}

function openUnitModal(unit?: LabOrganizationalUnit) {
  editingUnit.value = unit || null
  Object.assign(unitForm, {
    name: unit?.name || "",
    uid: unit?.uid || "",
    description: unit?.description || "",
    unitType: unit?.unit_type || "research_group",
    parentUnitId: unit?.parent_unit_id || (!canManageLab.value ? selectedUnit.value?.id || manageableUnits.value[0]?.id || null : null),
  })
  unitModalVisible.value = true
}

async function saveUnit() {
  await unitFormRef.value?.validate()
  if (!labInfo.value?.id)
    return
  saving.value = true
  try {
    if (editingUnit.value) {
      await putOrganizationalUnit(editingUnit.value.id, {
        name: unitForm.name,
        description: unitForm.description,
        unitType: unitForm.unitType,
        parentUnitId: unitForm.parentUnitId,
        updateParent: canManageLab.value,
      })
    }
    else {
      await postOrganizationalUnit({
        labId: String(labInfo.value.id),
        uid: unitForm.uid,
        name: unitForm.name,
        description: unitForm.description,
        unitType: unitForm.unitType,
        parentUnitId: unitForm.parentUnitId,
      })
    }
    unitModalVisible.value = false
    message.success($t("page.labs.access.saved"))
    await load()
  }
  finally {
    saving.value = false
  }
}

async function removeSelectedUnit() {
  if (!selectedUnit.value)
    return
  await deleteOrganizationalUnit(selectedUnit.value.id)
  message.success($t("page.labs.access.saved"))
  selectedUnitId.value = null
  await load()
}

const memberModalVisible = ref(false)
const memberForm = reactive({ userId: null as string | null, membershipRole: "member" as OrganizationalUnitMembershipRole })
const availableMemberOptions = computed(() => {
  const currentIds = new Set(selectedUnit.value?.members.map(member => member.id) || [])
  return labMembers.value
    .filter(member => !currentIds.has(String(member.id)))
    .map(member => ({ label: `${member.name || member.username} (@${member.username})`, value: String(member.id) }))
})

function roleLabel(role: OrganizationalUnitMembershipRole) {
  return role === "manager" ? $t("page.labs.access.unitManager") : $t("page.labs.access.unitMember")
}

function openMemberModal() {
  memberForm.userId = null
  memberForm.membershipRole = "member"
  memberModalVisible.value = true
}

async function saveMember() {
  if (!selectedUnit.value || !memberForm.userId)
    return
  saving.value = true
  try {
    await putOrganizationalUnitMember(selectedUnit.value.id, { userId: memberForm.userId, membershipRole: memberForm.membershipRole })
    memberModalVisible.value = false
    message.success($t("page.labs.access.saved"))
    await load()
  }
  finally {
    saving.value = false
  }
}

async function updateMemberRole(member: OrganizationalUnitMember, role: OrganizationalUnitMembershipRole) {
  if (!selectedUnit.value)
    return
  await putOrganizationalUnitMember(selectedUnit.value.id, { userId: member.id, membershipRole: role })
  await load()
}

async function removeMember(member: OrganizationalUnitMember) {
  if (!selectedUnit.value)
    return
  await deleteOrganizationalUnitMember(selectedUnit.value.id, member.id)
  message.success($t("page.labs.access.saved"))
  await load()
}

watch(() => labInfo.value?.id, load, { immediate: true })
</script>

<style scoped>
.organization-workspace { display: grid; grid-template-columns: minmax(240px, 340px) minmax(0, 1fr); min-height: 520px; border: 1px solid var(--n-border-color, #e5e7eb); }
.organization-tree-pane { border-right: 1px solid var(--n-border-color, #e5e7eb); padding: 16px; }
.organization-detail-pane { display: flex; min-width: 0; flex-direction: column; padding: 20px; }
.pane-header, .detail-header, .member-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.pane-header { margin-bottom: 16px; }
.pane-header h3, .detail-header h3 { margin: 0; font-size: 16px; }
.pane-header span, .detail-header p { margin: 4px 0 0; color: #6b7280; font-size: 12px; }
.member-toolbar { margin: 24px 0 12px; border-bottom: 1px solid #e5e7eb; padding-bottom: 10px; }
.member-toolbar span { margin-left: 8px; color: #6b7280; font-size: 12px; }
@media (max-width: 760px) {
  .organization-workspace { grid-template-columns: 1fr; }
  .organization-tree-pane { border-right: 0; border-bottom: 1px solid #e5e7eb; }
  .organization-detail-pane { min-height: 360px; padding: 16px; }
}
</style>
