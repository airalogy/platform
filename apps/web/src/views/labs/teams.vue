<template>
  <div class="teams-workspace">
    <aside class="team-tree-pane">
      <div class="pane-header">
        <div>
          <h3>{{ $t("page.labs.access.teams") }}</h3>
          <span>{{ $t("page.labs.access.teamCount", { count: teams.length }) }}</span>
        </div>
        <n-tooltip v-if="canCreateTeam">
          <template #trigger>
            <n-button quaternary circle type="primary" @click="openTeamModal()">
              <template #icon>
                <icon-ion-add-outline />
              </template>
            </n-button>
          </template>
          {{ $t("page.labs.access.createTeam") }}
        </n-tooltip>
      </div>
      <n-spin :show="loading">
        <n-tree
          v-if="treeData.length"
          block-line
          default-expand-all
          :data="treeData"
          :selected-keys="selectedTeamId ? [selectedTeamId] : []"
          @update:selected-keys="selectTeam"
        />
        <n-empty v-else :description="$t('page.labs.access.noTeams')" class="py-12" />
      </n-spin>
    </aside>

    <section class="team-detail-pane">
      <template v-if="selectedTeam">
        <header class="detail-header">
          <div class="min-w-0">
            <div class="flex items-center gap-2">
              <h3 class="truncate">
                {{ selectedTeam.name }}
              </h3>
              <n-tag size="small" :bordered="false">
                {{ selectedTeam.uid }}
              </n-tag>
            </div>
            <p>{{ selectedTeam.description || $t("page.labs.access.noDescription") }}</p>
          </div>
          <n-space v-if="canManageSelectedTeam">
            <n-tooltip>
              <template #trigger>
                <n-button quaternary circle @click="openTeamModal(selectedTeam)">
                  <template #icon>
                    <icon-ion-pencil-outline />
                  </template>
                </n-button>
              </template>
              {{ $t("common.edit") }}
            </n-tooltip>
            <n-popconfirm @positive-click="removeSelectedTeam">
              <template #trigger>
                <n-button quaternary circle type="error">
                  <template #icon>
                    <icon-ion-trash-outline />
                  </template>
                </n-button>
              </template>
              {{ $t("page.labs.access.deleteTeamConfirm") }}
            </n-popconfirm>
          </n-space>
        </header>

        <div class="member-toolbar">
          <div>
            <strong>{{ $t("page.labs.members") }}</strong>
            <span>{{ selectedTeam.members.length }}</span>
          </div>
          <n-button v-if="canManageSelectedTeam" type="primary" size="small" @click="openMemberModal">
            <template #icon>
              <icon-local-user-plus />
            </template>
            {{ $t("common.addMember") }}
          </n-button>
        </div>

        <n-data-table
          :columns="memberColumns"
          :data="selectedTeam.members"
          :row-key="row => row.id"
          :bordered="false"
          :single-line="false"
        />
      </template>
      <n-empty v-else :description="$t('page.labs.access.selectTeam')" class="m-auto" />
    </section>
  </div>

  <n-modal v-model:show="teamModalVisible" preset="dialog" :title="editingTeam ? $t('page.labs.access.editTeam') : $t('page.labs.access.createTeam')" :show-icon="false">
    <n-form ref="teamFormRef" :model="teamForm" :rules="teamRules" label-placement="top" class="mt-4">
      <n-form-item :label="$t('common.name')" path="name">
        <n-input v-model:value="teamForm.name" maxlength="64" show-count />
      </n-form-item>
      <n-form-item v-if="!editingTeam" :label="$t('page.labs.access.teamId')" path="uid">
        <n-input v-model:value="teamForm.uid" placeholder="molecular_biology" />
      </n-form-item>
      <n-form-item v-if="!editingTeam || canManageLab" :label="$t('page.labs.access.parentTeam')">
        <n-tree-select
          v-model:value="teamForm.parentGroupId"
          clearable
          :options="parentOptions"
          :placeholder="$t('page.labs.access.rootTeam')"
        />
      </n-form-item>
      <n-form-item :label="$t('common.description')">
        <n-input v-model:value="teamForm.description" type="textarea" maxlength="256" show-count />
      </n-form-item>
    </n-form>
    <template #action>
      <n-button @click="teamModalVisible = false">
        {{ $t("common.cancel") }}
      </n-button>
      <n-button type="primary" :loading="saving" @click="saveTeam">
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
        <n-select v-model:value="memberForm.membershipRole" :options="teamRoleOptions" />
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
import type { LabTeam, TeamMember, TeamMembershipRole } from "@/service/api/access"
import type { DataTableColumns, FormInst, FormRules, TreeOption } from "naive-ui"
import { useClosableMessage } from "@/composables"
import { LabRole } from "@/enum"
import {
  deleteTeam,
  deleteTeamMember,
  fetchLabTeams,
  postTeam,
  putTeam,
  putTeamMember,
} from "@/service/api/access"
import { fetchLabMemberList } from "@/service/api/labs"
import { useAuthStore } from "@/store/modules/auth"
import { $t } from "@airalogy/shared/locales"
import { NButton, NPopconfirm, NSelect, NTag } from "naive-ui"
import { useLabInfoStore } from "./hooks/useLabsInfoStore"

defineOptions({ name: "LabTeams" })

const message = useClosableMessage()
const { labInfo, userLabRole } = useLabInfoStore()!
const { userInfo } = useAuthStore()
const canManageLab = computed(() => userLabRole.value === LabRole.OWNER || userLabRole.value === LabRole.MANAGER)
const loading = ref(false)
const saving = ref(false)
const teams = ref<LabTeam[]>([])
const labMembers = ref<Api.Lab.MemberListItem[]>([])
const selectedTeamId = ref<number | null>(null)
const selectedTeam = computed(() => teams.value.find(team => team.id === selectedTeamId.value) || null)
const editingTeam = ref<LabTeam | null>(null)
const teamRoleOptions = computed(() => [
  { label: $t("page.labs.access.teamManager"), value: "manager" },
  { label: $t("page.labs.access.teamMember"), value: "member" },
])

function canManageTeam(team: LabTeam | null) {
  if (!team)
    return false
  if (canManageLab.value)
    return true
  const byId = new Map(teams.value.map(item => [item.id, item]))
  const visited = new Set<number>()
  let current: LabTeam | undefined = team
  while (current && !visited.has(current.id)) {
    visited.add(current.id)
    if (current.members.some(member => member.id === String(userInfo.id) && member.membership_role === "manager"))
      return true
    current = current.parent_group_id ? byId.get(current.parent_group_id) : undefined
  }
  return false
}

const canManageSelectedTeam = computed(() => canManageTeam(selectedTeam.value))
const manageableTeams = computed(() => teams.value.filter(team => canManageTeam(team)))
const canCreateTeam = computed(() => canManageLab.value || manageableTeams.value.length > 0)

function buildTree(parentId: number | null = null, excludedId?: number): TreeOption[] {
  return teams.value
    .filter(team => team.parent_group_id === parentId && team.id !== excludedId)
    .map(team => ({
      key: team.id,
      label: team.name,
      children: buildTree(team.id, excludedId),
    }))
}

const treeData = computed(() => buildTree())
const parentOptions = computed(() => canManageLab.value
  ? buildTree(null, editingTeam.value?.id)
  : manageableTeams.value
    .filter(team => team.id !== editingTeam.value?.id)
    .map(team => ({ key: team.id, label: team.name })))

async function load() {
  if (!labInfo.value?.id)
    return
  loading.value = true
  try {
    const [teamResult, memberResult] = await Promise.all([
      fetchLabTeams(String(labInfo.value.id)),
      fetchLabMemberList(String(labInfo.value.id), { page: 1, pageSize: 1000 }),
    ])
    teams.value = teamResult.data?.teams || []
    labMembers.value = memberResult?.users || []
    if (!selectedTeamId.value || !teams.value.some(team => team.id === selectedTeamId.value)) {
      selectedTeamId.value = teams.value[0]?.id || null
    }
  }
  finally {
    loading.value = false
  }
}

function selectTeam(keys: Array<string | number>) {
  selectedTeamId.value = Number(keys[0]) || null
}

const memberColumns = computed<DataTableColumns<TeamMember>>(() => [
  {
    title: $t("common.name"),
    key: "name",
    render: row => h("div", [h("strong", row.name || row.username), h("div", { class: "text-xs text-gray-500" }, `@${row.username}`)]),
  },
  {
    title: $t("common.role"),
    key: "membership_role",
    width: 180,
    render: row => canManageSelectedTeam.value
      ? h(NSelect, {
        value: row.membership_role,
        options: teamRoleOptions.value,
        size: "small",
        onUpdateValue: (value: TeamMembershipRole) => updateMemberRole(row, value),
      })
      : h(NTag, { size: "small", bordered: false }, { default: () => roleLabel(row.membership_role) }),
  },
  {
    title: "",
    key: "actions",
    width: 56,
    render: row => canManageSelectedTeam.value
      ? h(NPopconfirm, { onPositiveClick: () => removeMember(row) }, {
        trigger: () => h(NButton, { quaternary: true, circle: true, type: "error", size: "small" }, { default: () => h("span", { class: "i-ion-trash-outline" }) }),
        default: () => $t("page.labs.access.removeMemberConfirm"),
      })
      : null,
  },
])

const teamModalVisible = ref(false)
const teamFormRef = ref<FormInst | null>(null)
const teamForm = reactive({ name: "", uid: "", description: "", parentGroupId: null as number | null })
const teamRules: FormRules = {
  name: { required: true, message: $t("page.labs.access.nameRequired"), trigger: ["input", "blur"] },
  uid: { required: true, pattern: /^[a-z][a-z0-9_]{2,31}$/, message: $t("page.labs.access.teamIdHint"), trigger: ["input", "blur"] },
}

function openTeamModal(team?: LabTeam) {
  editingTeam.value = team || null
  Object.assign(teamForm, {
    name: team?.name || "",
    uid: team?.uid || "",
    description: team?.description || "",
    parentGroupId: team?.parent_group_id || (!canManageLab.value ? selectedTeam.value?.id || manageableTeams.value[0]?.id || null : null),
  })
  teamModalVisible.value = true
}

async function saveTeam() {
  await teamFormRef.value?.validate()
  if (!labInfo.value?.id)
    return
  saving.value = true
  try {
    if (editingTeam.value) {
      await putTeam(editingTeam.value.id, {
        name: teamForm.name,
        description: teamForm.description,
        parentGroupId: teamForm.parentGroupId,
        updateParent: canManageLab.value,
      })
    }
    else {
      await postTeam({
        labId: String(labInfo.value.id),
        uid: teamForm.uid,
        name: teamForm.name,
        description: teamForm.description,
        parentGroupId: teamForm.parentGroupId,
      })
    }
    teamModalVisible.value = false
    message.success($t("page.labs.access.saved"))
    await load()
  }
  finally {
    saving.value = false
  }
}

async function removeSelectedTeam() {
  if (!selectedTeam.value)
    return
  await deleteTeam(selectedTeam.value.id)
  message.success($t("page.labs.access.saved"))
  selectedTeamId.value = null
  await load()
}

const memberModalVisible = ref(false)
const memberForm = reactive({ userId: null as string | null, membershipRole: "member" as TeamMembershipRole })
const availableMemberOptions = computed(() => {
  const currentIds = new Set(selectedTeam.value?.members.map(member => member.id) || [])
  return labMembers.value
    .filter(member => !currentIds.has(String(member.id)))
    .map(member => ({ label: `${member.name || member.username} (@${member.username})`, value: String(member.id) }))
})

function roleLabel(role: TeamMembershipRole) {
  return role === "manager" ? $t("page.labs.access.teamManager") : $t("page.labs.access.teamMember")
}

function openMemberModal() {
  memberForm.userId = null
  memberForm.membershipRole = "member"
  memberModalVisible.value = true
}

async function saveMember() {
  if (!selectedTeam.value || !memberForm.userId)
    return
  saving.value = true
  try {
    await putTeamMember(selectedTeam.value.id, { userId: memberForm.userId, membershipRole: memberForm.membershipRole })
    memberModalVisible.value = false
    message.success($t("page.labs.access.saved"))
    await load()
  }
  finally {
    saving.value = false
  }
}

async function updateMemberRole(member: TeamMember, role: TeamMembershipRole) {
  if (!selectedTeam.value)
    return
  await putTeamMember(selectedTeam.value.id, { userId: member.id, membershipRole: role })
  await load()
}

async function removeMember(member: TeamMember) {
  if (!selectedTeam.value)
    return
  await deleteTeamMember(selectedTeam.value.id, member.id)
  message.success($t("page.labs.access.saved"))
  await load()
}

watch(() => labInfo.value?.id, load, { immediate: true })
</script>

<style scoped>
.teams-workspace { display: grid; grid-template-columns: minmax(220px, 300px) minmax(0, 1fr); min-height: 520px; border: 1px solid var(--n-border-color, #e5e7eb); }
.team-tree-pane { border-right: 1px solid var(--n-border-color, #e5e7eb); padding: 16px; }
.team-detail-pane { display: flex; min-width: 0; flex-direction: column; padding: 20px; }
.pane-header, .detail-header, .member-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.pane-header { margin-bottom: 16px; }
.pane-header h3, .detail-header h3 { margin: 0; font-size: 16px; }
.pane-header span, .detail-header p { margin: 4px 0 0; color: #6b7280; font-size: 12px; }
.member-toolbar { margin: 24px 0 12px; border-bottom: 1px solid #e5e7eb; padding-bottom: 10px; }
.member-toolbar span { margin-left: 8px; color: #6b7280; font-size: 12px; }
@media (max-width: 760px) {
  .teams-workspace { grid-template-columns: 1fr; }
  .team-tree-pane { border-right: 0; border-bottom: 1px solid #e5e7eb; }
  .team-detail-pane { min-height: 360px; padding: 16px; }
}
</style>
