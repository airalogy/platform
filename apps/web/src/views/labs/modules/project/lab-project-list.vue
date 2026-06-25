<template>
  <n-list clickable hoverable>
    <template v-for="group in groupedProjectList" :key="group.parent.id">
      <n-list-item class="overflow-hidden">
        <template #prefix>
          <project-icon class="align-middle" />
        </template>
        <lab-project-item
          :type="props.type" :item="group.parent" :is-compact="false" class="max-w-full w-fit" :fetch-count="props.fetchCount"
          :group-id="groupInfo?.id"
        >
          <global-role-tag
            v-if="type === 'group'"
            :item="group.parent"
            :is-compact="false"
            type="group"
            :project-type="group.parent?.type"
            class="ml-4"
          />
        </lab-project-item>
        <template #suffix>
          <div v-if="checkPermission(group.parent)" class="flex items-center">
            <n-button
              v-if="props.type === 'group'"
              class="mr-3"
              size="small"
              @click="showRoleChangeDialog(group.parent as any as Api.Groups.GroupProjectItem) "
            >
              Change Role
            </n-button>
            <edit-button :item="group.parent" type="project" />
          </div>
        </template>
      </n-list-item>

      <div
        v-if="group.children.length"
        class="mb-4 ml-10 overflow-hidden border border-gray-200 rounded-lg bg-gray-50/60"
      >
        <div class="flex items-center justify-between border-b border-gray-200 px-4 py-2 text-xs text-gray-500 font-600">
          <span>{{ $t("page.project.settingsPage.subprojectsTitle") }}</span>
          <span>{{ getSubprojectCountLabel(group.children.length) }}</span>
        </div>
        <div class="divide-y divide-gray-100">
          <div v-for="child in group.children" :key="child.id" class="flex items-start gap-3 px-4 py-3">
            <project-icon class="mt-1 shrink-0 align-middle opacity-70" />
            <lab-project-item
              :type="props.type"
              :item="child"
              :is-compact="false"
              class="max-w-full min-w-0 flex-1"
              :fetch-count="props.fetchCount"
              :group-id="groupInfo?.id"
            />
            <div v-if="checkPermission(child)" class="ml-2 flex items-center">
              <edit-button :item="child" type="project" />
            </div>
          </div>
        </div>
      </div>
    </template>
  </n-list>
</template>

<script setup lang="tsx">
import RoleChangeDialog from "@/components/common/role-change-dialog.vue"
import { getProjectRoleInfo, PROJECT_OWNER_AND_MANAGER, useClosableMessage } from "@/composables"
import { LAB_OWNER_AND_MANAGER } from "@/composables/useLabPermissions"
import { ProjectRole } from "@/enum"
import { putGroupsProjectRole } from "@/service/api/groups"
import { $t } from "@airalogy/shared/locales"
import { useDialog } from "naive-ui"
import { useOrProvideLabInfoStore } from "../../hooks/useLabsInfoStore"
import LabProjectItem from "./lab-project-item.vue"

defineOptions({ name: "LabOrGroupProjectList" })
const props = withDefaults(defineProps<IProps>(), {
  list: () => [],
  type: "lab",
  groupInfo: null,
  fetchCount: true,
})

const emit = defineEmits<IEmits>()

interface IProps {
  list: (Api.Project.MyProjectInfo | Api.Groups.GroupProjectItem)[]
  type?: "lab" | "group"
  groupInfo?: Api.Groups.MyGroupsInfo | null
  labInfo?: Api.Lab.LabInfo | null
  fetchCount?: boolean
}

interface IEmits {
  (e: "update:role", data: { project_id: string, role: ProjectRole }): void
}

interface ProjectGroup {
  parent: Api.Project.MyProjectInfo
  children: Api.Project.MyProjectInfo[]
}

const { isManager } = useOrProvideLabInfoStore(null)

function checkPermission(item: Api.Project.MyProjectInfo | Api.Groups.GroupProjectItem) {
  if (isManager.value) {
    return true
  }

  const { type } = props

  if (type === "lab") {
    const { user_role, user_lab_role } = item as Api.Project.MyProjectInfo
    return LAB_OWNER_AND_MANAGER.includes(user_lab_role) || PROJECT_OWNER_AND_MANAGER.includes(user_role)
  }

  return false
}

const projectList = computed<Api.Project.MyProjectInfo[]>(() => {
  const { list, type, labInfo } = props
  if (type === "lab") {
    return list as Api.Project.MyProjectInfo[]
  }

  if (!labInfo) {
    return []
  }

  const { uid: labUid } = labInfo

  return list.map((item) => {
    const { group_role, ...rest } = item as Api.Groups.GroupProjectItem

    return {
      ...rest,
      lab_uid: labUid,
      user_role: group_role,
      group_role,
    } as any as Api.Project.MyProjectInfo
  })
})

const groupedProjectList = computed<ProjectGroup[]>(() => {
  if (props.type !== "lab") {
    return projectList.value.map(item => ({ parent: item, children: [] }))
  }

  const items = projectList.value
  const rootList: Api.Project.MyProjectInfo[] = []
  const childrenMap = new Map<string, Api.Project.MyProjectInfo[]>()
  const itemIds = new Set(items.map(item => item.id))

  for (const item of items) {
    const parentId = item.parent_project_id
    if (!parentId || !itemIds.has(parentId)) {
      rootList.push(item)
      continue
    }

    const siblings = childrenMap.get(parentId) || []
    siblings.push(item)
    childrenMap.set(parentId, siblings)
  }

  return rootList.map(parent => ({
    parent,
    children: childrenMap.get(parent.id) || [],
  }))
})

function getSubprojectCountLabel(count: number) {
  return count === 1
    ? $t("page.project.settingsPage.subprojectCountSingle", { count })
    : $t("page.project.settingsPage.subprojectCountPlural", { count })
}

const message = useClosableMessage()
const dialog = useDialog()
// const roleRef = computed(() => (props.groupInfo?.user_role))
// const { projectRoleOptions } = useRoleDescription(roleRef, "group")

function showRoleChangeDialog(item: Api.Groups.GroupProjectItem) {
  const currentRole = item.group_role
  const newRole = ref<ProjectRole >(currentRole)
  const handleUpdateRole = (value: ProjectRole) => {
    newRole.value = value
  }

  const options = getProjectRoleInfo(ProjectRole.COLLABORATOR, item.type)

  dialog.info({
    title: `Change the ${props.type} role of ${item.name}?`,
    content: () =>
      (
        <RoleChangeDialog
          availableRoles={options}
          currentRole={currentRole}
          role={newRole.value}
          onUpdate:role={handleUpdateRole}
        />
      ),
    positiveText: "Confirm",
    negativeText: "Cancel",
    showIcon: false,
    class: "!w-fit",
    contentClass: "w-40vw",
    onPositiveClick: () => {
      if (newRole.value !== currentRole) {
        handleChangeRole(item, newRole.value)
      }
    },
  })
}

async function handleChangeRole(
  item: Api.Groups.GroupProjectItem,
  val: ProjectRole,
) {
  const { id, name } = item
  const groupId = props.groupInfo?.id

  if (!groupId) {
    message.error("Invalid group id.")
    return
  }

  const { data } = await putGroupsProjectRole(groupId, {
    projectId: id,
    role: val,
  })

  if (data) {
    message.success(`Successfully changed project "${name}" group role to "${ProjectRole[val]}". `)
    emit("update:role", data)
  }
  else {
    message.error(`Failed changing project "${name}" group role to "${ProjectRole[val]}". `)
  }
}
</script>

<style scoped lang="sass">
:deep(.n-list-item__main)
  flex-shrink: 1!important
  overflow: hidden
</style>
