<template>
  <n-list class="member-list" hoverable>
    <n-list-item v-for="item in props.list" :key="item.id" class="member-list__item">
      <template #prefix>
        <n-avatar
          v-if="item.avatar_url"
          :src="item.avatar_url"
          :size="40"
          color="transparent"
          object-fit="cover"
          class="vertical-middle"
        />
        <role-icon v-else :type="props.type" :role="roleRecord[item.id]" />
      </template>
      <global-member-item
        :item="item"
        :is-compact="false"
        :type="props.type"
        :project-type="projectInfo?.type"
        class="min-w-0 w-fit"
      />
      <template v-if="checkPermission(item)" #suffix>
        <n-dropdown
          v-if="isMobile"
          trigger="click"
          :options="mobileActionOptions(item)"
          @select="handleMobileAction($event, item)"
        >
          <n-button
            quaternary
            circle
            size="small"
            :aria-label="$t('common.actions')"
            :title="$t('common.actions')"
          >
            <template #icon>
              <icon-tabler-dots-vertical />
            </template>
          </n-button>
        </n-dropdown>
        <div v-else class="flex items-center">
          <n-button
            v-if="props.type === 'lab' && checkPermission(item)"
            class="mr-3"
            size="small"
            @click="showUpdateLabAliasDialog(item as Api.Lab.MemberListItem)"
          >
            {{ $t("common.setAlias") }}
          </n-button>
          <n-button
            v-if="props.type === 'lab' && instanceStore.isSingleLab && checkPermission(item)"
            class="mr-3"
            size="small"
            :loading="resettingUserId === item.id"
            @click="showPasswordResetLink(item as Api.Lab.MemberListItem)"
          >
            {{ $t("page.instance.createResetLink") }}
          </n-button>
          <n-button
            v-if="props.type !== 'group'"
            class="mr-3"
            size="small"
            @click="showRoleChangeDialog(item)"
          >
            {{ $t("common.changeRole") }}
          </n-button>
          <delete-button v-if="!checkIsSelf(item)" @click="handleRemoveUser(item)" />
        </div>
      </template>
    </n-list-item>
  </n-list>
</template>

<script setup lang="tsx">
import type { RoleInfo } from "@/composables"
import type { DropdownOption } from "naive-ui"
import { getRoleLabel, projectRoleHierarchyPrivate, useBasicLayout, useClosableMessage, useRoleDescription } from "@/composables"
import { useLabPermissions } from "@/composables/useLabPermissions"
import { useProjectPermissions } from "@/composables/useProjectPermissions"
import { LabRole, ProjectRole, ProjectType } from "@/enum"
import { deleteGroupsMember } from "@/service/api/groups"
import { createPasswordResetLink } from "@/service/api/instance"
import { deleteLabMember, putLabMember } from "@/service/api/labs"
import { deleteProjectMember, putProjectMember } from "@/service/api/projects"
import { useAppStore } from "@/store/modules/app"
import { useAuthStore } from "@/store/modules/auth"
import { useInstanceStore } from "@/store/modules/instance"
import { useOrProvideLabInfoStore } from "@/views/labs/hooks/useLabsInfoStore"
import UpdateAliasModal from "@/views/labs/modules/lab/UpdateAliasModal.vue"
import { useOrProvideProjectInfoStore } from "@/views/project-protocols/hooks/useProjectInfoStore"
import { copyToClip } from "@airalogy/shared"
import { useDialog } from "naive-ui"
import { useI18n } from "vue-i18n"
import RoleChangeDialog from "./role-change-dialog.vue"

defineOptions({ name: "GlobalMemberList" })

const props = withDefaults(defineProps<IProps>(), {
  list: () => [],
})

const emit = defineEmits<IEmits>()

const authStore = useAuthStore()
const instanceStore = useInstanceStore()
const { isMobile } = useBasicLayout()
const resettingUserId = ref("")
const { projectInfo } = useOrProvideProjectInfoStore(null)
const { labInfo } = useOrProvideLabInfoStore(null)

const {
  canAssignRoles,
  userRole: userProjectRole,
} = useProjectPermissions(projectInfo)

const {
  isOwner: isLabOwner,
  isManager: isLabManager,
} = useLabPermissions(labInfo)

interface IProps {
  type: "lab" | "project" | "group"
  id: string | string[] | number
  list: (Api.Lab.MemberListItem | Api.Project.MemberListItem | Api.Groups.MemberListItem)[]
}

interface IEmits {
  (
    e: "update:role",
    payload: { id: string | number, role: Api.Lab.LabRole | Api.Project.ProjectRole },
  ): void
}

const roleRecord = computed(() => {
  return props.list.reduce(
    (acc, it) => {
      const { id } = it
      if (props.type === "lab") {
        acc[id] = (it as Api.Lab.MemberListItem).lab_role
      }
      else if (props.type === "project") {
        acc[id] = (it as Api.Project.MemberListItem).project_role
      }

      return acc
    },
    {} as Record<string, Api.Lab.LabRole>,
  )
})

// const projectRoleOptions: { label: string, value: ProjectRole }[] = Object.entries(ProjectRole)
//   .filter(([, value]) => typeof value === "number")
//   .map(([key, value]) => ({
//     label: key.charAt(0).toUpperCase() + key.slice(1).toLowerCase(),
//     value: value as ProjectRole,
//   }))
const projectType = computed(() => projectInfo.value?.type)
const { projectRoleOptions } = useRoleDescription(userProjectRole, toRef(props.type), projectType, true)

const options = computed((): (RoleInfo | { label: string, value: any })[] => {
  if (props.type === "project") {
    return projectRoleOptions.value
  }
  if (props.type === "group") {
    return [
      { label: "Manager", value: LabRole.MANAGER },
      { label: "Member", value: LabRole.MEMBER },
    ]
  }
  // lab
  return [
    { label: "Manager", value: LabRole.MANAGER },
    { label: "Member", value: LabRole.MEMBER },
  ]
})

const dialog = useDialog()
const message = useClosableMessage()
const { reloadPage } = useAppStore()
const { t } = useI18n()

type MobileMemberAction = "alias" | "reset-password" | "change-role" | "remove"

function mobileActionOptions(
  item: Api.Lab.MemberListItem | Api.Project.MemberListItem | Api.Groups.MemberListItem,
): DropdownOption[] {
  return [
    ...(props.type === "lab" ? [{ label: t("common.setAlias"), key: "alias" }] : []),
    ...(props.type === "lab" && instanceStore.isSingleLab
      ? [{ label: t("page.instance.createResetLink"), key: "reset-password" }]
      : []),
    ...(props.type !== "group" ? [{ label: t("common.changeRole"), key: "change-role" }] : []),
    ...(!checkIsSelf(item) ? [{ label: t("common.remove"), key: "remove" }] : []),
  ]
}

function handleMobileAction(
  key: string | number,
  item: Api.Lab.MemberListItem | Api.Project.MemberListItem | Api.Groups.MemberListItem,
) {
  switch (key as MobileMemberAction) {
    case "alias":
      showUpdateLabAliasDialog(item as Api.Lab.MemberListItem)
      break
    case "reset-password":
      showPasswordResetLink(item as Api.Lab.MemberListItem)
      break
    case "change-role":
      showRoleChangeDialog(item)
      break
    case "remove":
      handleRemoveUser(item)
      break
  }
}

async function showPasswordResetLink(item: Api.Lab.MemberListItem) {
  resettingUserId.value = item.id
  try {
    const { data } = await createPasswordResetLink(String(item.id))
    if (!data)
      return

    const resetUrl = data.url
    dialog.info({
      title: t("page.instance.resetLinkFor", { name: item.name || item.username }),
      content: () => (
        <div class="space-y-3">
          <n-input value={resetUrl} readonly type="textarea" autosize={{ minRows: 2, maxRows: 4 }} />
          <div class="text-xs text-gray-500">
            {t("page.instance.linkExpiresAt", {
              time: new Intl.DateTimeFormat(undefined, {
                dateStyle: "medium",
                timeStyle: "short",
              }).format(new Date(data.expires_at)),
            })}
          </div>
          <n-button
            type="primary"
            onClick={async () => {
              await copyToClip(resetUrl)
              message.success(t("page.instance.linkCopied"))
            }}
          >
            {t("page.instance.copyResetLink")}
          </n-button>
        </div>
      ),
      positiveText: t("common.close"),
      showIcon: false,
    })
  }
  finally {
    resettingUserId.value = ""
  }
}

interface AliasDialogConfig {
  title: string
  alias?: string | null
  label: string
  placeholder: string
  requiredMessage: string
  required?: boolean
  onSubmit: (alias: string) => Promise<void>
}

function openAliasDialog(config: AliasDialogConfig) {
  const aliasRef = ref<InstanceType<typeof UpdateAliasModal>>()
  const dialogInstance = dialog.info({
    title: config.title,
    content: () =>
      h(UpdateAliasModal, {
        ref: aliasRef,
        alias: config.alias ?? "",
        label: config.label,
        placeholder: config.placeholder,
        requiredMessage: config.requiredMessage,
        required: config.required ?? true,
      }),
    positiveText: "Confirm",
    negativeText: "Cancel",
    showIcon: false,
    onPositiveClick: async () => {
      dialogInstance.loading = true
      try {
        const alias = await aliasRef.value?.getAlias()
        await config.onSubmit((alias as string) || "")
        message.success("Alias updated successfully")
      }
      catch (e) {
        message.error((e as Error).message)
        return false
      }
      finally {
        dialogInstance.loading = false
      }
    },
  })
}

function handleRemoveUser(item: Api.Lab.MemberListItem | Api.Project.MemberListItem | Api.Groups.MemberListItem) {
  const { id: userId, username, name: userDisplayName } = item
  const { id: parentId, type } = props

  if (!userId || !parentId || Array.isArray(parentId)) {
    message.error(t("common.memberRemoveFailed"))
    return
  }

  const orgName = type === "group"
    ? t("common.group")
    : type === "project"
      ? (projectInfo.value?.name || t("common.project"))
      : (labInfo.value?.name || t("common.lab"))
  const roleName = getRoleLabel(
    type === "project" || type === "group"
      ? (item as Api.Project.MemberListItem).project_role
      : type === "lab" ? (item as Api.Lab.MemberListItem).lab_role : null,
    type,
  ) || t("role.member")

  dialog.error({
    title: orgName ? t("common.memberRemoveTitleWithOrg", { name: orgName }) : t("common.memberRemoveTitle"),
    showIcon: false,
    content: () => (
      <div>
        <div class="mb-2">{t("common.memberRemoveConfirm", { role: roleName, name: userDisplayName })}</div>

        <div class="flex items-center rounded-lg bg-gray-100 p-2">
          {item.avatar_url
            ? (
                <n-avatar
                  src={item.avatar_url}
                  size="small"
                  color="transparent"
                  object-fit="cover"
                  class="shrink-0"
                />
              )
            : <role-icon type={props.type} role={roleRecord.value[item.id]} />}

          <router-link
            to={{ name: "user-profile", params: { username: item.username } }}
            target="_blank"
            class="ml-2 !hover:router-link"
          >
            <span>{item.name || item.username}</span>
          </router-link>
        </div>
      </div>
    ),
    positiveText: t("common.remove"),
    negativeText: t("common.cancel"),
    onPositiveClick: async () => {
      try {
        if (type === "lab") {
          const success = await deleteLabMember(parentId, userId)
          if (success) {
            message.success(t("common.memberRemoveSuccess", { name: userDisplayName || username }))
            await reloadPage(50)
            return
          }
        }
        if (type === "group") {
          const success = await deleteGroupsMember(parentId, userId)
          if (success) {
            message.success(t("common.memberRemoveSuccess", { name: userDisplayName || username }))
            await reloadPage(50)
            return
          }
        }
        if (type === "project") {
          const success = await deleteProjectMember(parentId, userId)
          if (success) {
            message.success(t("common.memberRemoveSuccess", { name: userDisplayName || username }))
            await reloadPage(50)
            return
          }
        }

        message.error("Failed to remove member")
      }
      catch (e) {
        message.error((e as Error).message)
      }
    },
  })
}

function showUpdateLabAliasDialog(item: Api.Lab.MemberListItem) {
  openAliasDialog({
    title: t("common.setAlias"),
    alias: item.lab_alias,
    label: t("common.labAliasLabel"),
    placeholder: t("common.labAliasPlaceholder"),
    requiredMessage: t("common.labAliasRequired"),
    onSubmit: async (alias) => {
      const labId = Array.isArray(props.id) ? props.id.join("") : props.id
      if (!labId) {
        message.error(t("common.memberRemoveFailed"))
        return
      }
      await putLabMember(labId, { userId: item.id, role: item.lab_role, alias })
      emit("update:role", { id: item.id, role: item.lab_role })
    },
  })
}

function showRoleChangeDialog(item: Api.Lab.MemberListItem | Api.Project.MemberListItem | Api.Groups.MemberListItem) {
  const isProject = props.type === "project"
  const currentRole = isProject
    ? (item as Api.Project.MemberListItem).project_role
    : (item as Api.Lab.MemberListItem).lab_role

  const newRole = ref<ProjectRole | LabRole >(currentRole)
  const handleUpdateRole = (value: ProjectRole | LabRole) => {
    newRole.value = value
  }
  dialog.info({
    title: `Change the ${props.type} role of ${item.name}?`,
    content: () =>
      (
        <RoleChangeDialog
          availableRoles={options.value as RoleInfo[]}
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
  item: Api.Lab.MemberListItem | Api.Project.MemberListItem | Api.Groups.MemberListItem,
  val: LabRole | ProjectRole,
) {
  const { type } = props

  if (type === "lab") {
    const { id: userId, username } = item as Api.Lab.MemberListItem

    const labId = Array.isArray(props.id) ? props.id.join("") : props.id
    if (!labId) {
      message.error(`Failed changing user ${username} to ${val}. `)
      return
    }

    const labAlias = (item as Api.Lab.MemberListItem).lab_alias
    const { data } = await putLabMember(labId, { role: val, userId, alias: labAlias })
    if (data) {
      message.success(`Successfully changed user "${username}" to "${LabRole[val]}". `)
      emit("update:role", { id: userId, role: val })
    }
    else {
      message.error(`Failed changing user "${username}" role to "${LabRole[val]}". `)
    }
  }
  else if (type === "project") {
    const { id: userId, username } = item as Api.Project.MemberListItem
    const projectId = Array.isArray(props.id) ? props.id.join("") : props.id
    if (!projectId) {
      message.error(`Failed changing user ${userId} to ${val}. `)
      return
    }

    if (projectType.value === ProjectType.PRIVATE && !projectRoleHierarchyPrivate.includes(val as ProjectRole)) {
      message.error("Invalid role for private project")
      return
    }
    const { data } = await putProjectMember(projectId, { role: val, userId })
    if (data) {
      message.success(`Successfully changed user "${username}" to "${ProjectRole[val]}". `)
      emit("update:role", { id: userId, role: val })
    }
    else {
      message.error(`Failed changing user "${userId}" role to "${ProjectRole[val]}". `)
    }
  }
}

function checkIsSelf(item: Api.Lab.MemberListItem | Api.Project.MemberListItem | Api.Groups.MemberListItem) {
  const { id: userId } = authStore.userInfo
  return item.id === userId
}

function checkPermission(item: Api.Lab.MemberListItem | Api.Project.MemberListItem | Api.Groups.MemberListItem) {
  const { id: currentUserId } = authStore.userInfo
  if (item.id === currentUserId) {
    return false
  }

  if (props.type === "project") {
    return canAssignRoles.value && toValue(userProjectRole) < (item as Api.Project.MemberListItem).project_role
  }

  if (props.type === "lab" || props.type === "group") {
    if (isLabOwner.value) {
      return true
    }
    if (isLabManager.value) {
      const targetUserRole = (item as Api.Lab.MemberListItem).lab_role
      return targetUserRole > LabRole.MANAGER
    }
  }

  return false
}
</script>

<style scoped lang="sass">
@media (max-width: 639px)
  :deep(.member-list__item)
    padding: 12px 8px

  :deep(.member-list__item .n-list-item__main)
    min-width: 0

  :deep(.member-list__item .n-list-item__prefix)
    margin-right: 10px

  :deep(.member-list__item .n-list-item__suffix)
    flex-shrink: 0
    margin-left: 8px
</style>
