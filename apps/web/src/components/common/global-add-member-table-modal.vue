<template>
  <n-button v-bind="props.buttonProps" @click.stop="showModal">
    <template v-if="props.showIcon" #icon>
      <icon-local-user-plus v-if="compact" />
      <add-circle-outline v-else />
    </template>
    {{ triggerLabel }}
  </n-button>
  <n-modal
    :show="isShown"
    preset="card"
    :title="$t('common.addMembers')"
    :bordered="false"
    size="huge"
    class="w-160"
    :mask-closable="false"
    @update:show="handleSetShow"
  >
    <div class="mb-5">
      <n-select
        v-model:value="currentSearchValue"
        size="large"
        :options="memberOptions"
        :render-label="renderLabel"
        :loading="loading"
        :clear-filter-after-select="true"
        :placeholder="$t('common.memberSearchPlaceholder')"
        remote
        clearable
        filterable
        :show="isShowMenu"
        :consistent-menu-width="false"
        @search="handleSearch"
        @clear="handleClear"
        @update:value="handleValueChange"
      />
    </div>

    <!-- Selected members table -->
    <n-table v-if="selectedUsers.length > 0" striped class="mb-5">
      <thead>
        <tr>
          <th style="width: 50px">
            {{ $t("common.avatar") }}
          </th>
          <th style="width: 150px">
            {{ $t("common.name") }}
          </th>
          <th style="width: 150px">
            {{ $t("common.alias") }}
          </th>
          <th style="width: 150px">
            {{ $t("common.role") }}
          </th>
          <th style="width: 60px">
            {{ $t("common.action") }}
          </th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="user in selectedUsers" :key="user.value">
          <td>
            <n-avatar
              :src="user.avatar || '/images/avatar_default.svg'"
              size="small"
              color="transparent"
              object-fit="cover"
            />
          </td>
          <td>
            <div class="flex flex-col">
              <span class="font-medium">{{ user.label }}</span>
              <span v-if="user.username" class="text-xs text-gray-500">@{{ user.username }}</span>
            </div>
          </td>
          <td>
            <n-input
              :value="user.alias"
              size="small"
              type="text"
              :placeholder="$t('common.aliasPlaceholder')"
              @input="(val) => handleAliasChange(user.value, val)"
            />
          </td>
          <td>
            <n-select
              :value="user.role"
              :options="getRoleOptions()"
              size="small"
              :consistent-menu-width="false"
              @update:value="(val) => handleRoleChange(user.value, val)"
            />
          </td>
          <td>
            <n-button
              size="small"
              tertiary
              type="error"
              @click="handleRemoveUser(user.value)"
            >
              {{ $t("common.remove") }}
            </n-button>
          </td>
        </tr>
      </tbody>
    </n-table>

    <div class="flex items-center justify-end">
      <n-button size="medium" class="mr-4" :disabled="loading" @click="handleCancel">
        {{ $t("common.cancel") }}
      </n-button>
      <n-button
        size="medium"
        type="primary"
        :disabled="loading || selectedUsers.length === 0"
        :loading="loading"
        @click="handleConfirm"
      >
        {{ $t("common.confirm") }}
      </n-button>
    </div>
  </n-modal>
</template>

<script setup lang="ts">
import type { ButtonProps, SelectOption, SelectRenderLabel } from "naive-ui"
import { useBoolean, useLoading, useShowModal } from "@/composables"
import { LabRole, ProjectRole } from "@/enum"
import { addGroupsMember } from "@/service/api/groups"
import { addLabMember } from "@/service/api/labs"
import { addProjectMember } from "@/service/api/projects"
import { fetchUserList } from "@/service/api/users"
import { useAuthStore } from "@/store/modules/auth"
import { useClosableMessage } from "@airalogy/composables"
import { $t } from "@airalogy/shared/locales"
import { useDebounceFn } from "@vueuse/core"
import AddCircleOutline from "~icons/ion/add-circle-outline"
import { NAvatar, NButton } from "naive-ui"
import { computed } from "vue"

interface IProps {
  showIcon?: boolean
  buttonProps?: ButtonProps & { class?: string }
  compact?: boolean
  trigger?: string
  type: "lab" | "project" | "group"
  currentList?: (Api.Project.MemberListItem | Api.Lab.MemberListItem | Api.Groups.MemberListItem)[]
  id: string
  isPrivate?: boolean
}

const props = withDefaults(defineProps<IProps>(), {
  showIcon: true,
  trigger: "",
  buttonProps: () => ({}),
  compact: true,
  type: "lab",
  currentList: () => [],
})

const emits = defineEmits<IEmits>()

interface UserItem {
  label: string
  value: string
  email: string
  avatar?: string
  username?: string
  role: Api.Lab.LabRole
  alias?: string
}

interface IEmits {
  (
    e: "modal:new-member",
    val: {
      label: string
      value: string
      email: string
      role: Api.Lab.LabRole
    }[],
  ): void
  (e: "modal:close"): void
  (e: "modal:open"): void
}

const message = useClosableMessage()
const { isShown, showModal, hideModal, setModalStatus } = useShowModal()
const { bool: isShowMenu, setFalse: hideMenu, setTrue: showMenu } = useBoolean()
const { loading, startLoading, endLoading } = useLoading()
const authStore = useAuthStore()
const triggerLabel = computed(() => props.trigger || $t("common.addMember"))

const memberOptions = ref<SelectOption[]>([])
const selectedUsers = ref<UserItem[]>([])
const currentSearchValue = ref<string | null>(null)

// Get default role based on type
function getDefaultRole(): Api.Lab.LabRole {
  if (props.type === "lab" || props.type === "group") {
    return LabRole.MEMBER
  }
  if (props.type === "project") {
    if (props.isPrivate) {
      return ProjectRole.RECORDER
    }
    else {
      return ProjectRole.COLLABORATOR
    }
  }
  return ProjectRole.EXPLORER
}

// Get available roles for dropdown
function getRoleOptions(): SelectOption[] {
  if (props.type === "lab" || props.type === "group") {
    return [
      { label: $t("role.manager"), value: LabRole.MANAGER },
      { label: $t("role.member"), value: LabRole.MEMBER },
    ]
  }

  if (props.type === "project") {
    const allRoles = [
      { label: $t("role.manager"), value: ProjectRole.MANAGER },
      { label: $t("role.collaborator"), value: ProjectRole.COLLABORATOR },
      { label: $t("role.recorder"), value: ProjectRole.RECORDER },
      { label: $t("role.recorder_self_only"), value: ProjectRole.RECORDER_SELF_ONLY },
      { label: $t("role.explorer"), value: ProjectRole.EXPLORER },
      { label: $t("role.explorer_self_only"), value: ProjectRole.EXPLORER_SELF_ONLY },
      { label: $t("role.viewer"), value: ProjectRole.VIEWER },
      { label: $t("role.viewer_self_only"), value: ProjectRole.VIEWER_SELF_ONLY },
    ]

    // For private project, only show limited roles
    if (props.isPrivate) {
      return allRoles.filter(({ value }) => value <= ProjectRole.RECORDER)
    }

    return allRoles
  }

  return []
}

const renderLabel: SelectRenderLabel = (option) => {
  return h(
    "div",
    {
      style: {
        display: "flex",
        alignItems: "center",
      },
    },
    [
      h(NAvatar, {
        src: (option.avatar as string) || "/images/avatar_default.svg",
        round: true,
        size: "small",
        objectFit: "cover",
      }),
      h(
        "div",
        {
          style: {
            marginLeft: "12px",
            padding: "4px 0",
          },
        },
        [
          h("div", null, {
            default: () => [
              h("span", null, { default: () => option.label }),
              option.username
                ? h("span", { style: { marginLeft: "4px", color: "#999", fontSize: "12px" } }, `(@${option.username as string})`)
                : null,
            ],
          }),
          h("div", { style: { color: "#999", fontSize: "12px" } }, option.email as string),
        ],
      ),
    ],
  )
}

function handleClearOption() {
  hideMenu()
  setTimeout(() => (memberOptions.value = []), 200)
}

function handleClear() {
  handleClearOption()
}

const handleSearch = useDebounceFn(async (val: string) => {
  if (!val) {
    handleClearOption()
    return
  }

  startLoading()
  const { id: userId } = authStore.userInfo
  try {
    const result = await fetchUserList(val)
    if (result) {
      const { data } = result
      showMenu()
      if (Array.isArray(data)) {
        memberOptions.value = data
          .filter(({ id }) => id !== userId)
          .map(({ name, username, id, email, avatar_url }): SelectOption => ({
            label: name || username,
            username,
            value: id,
            email,
            avatar: avatar_url,
          }))
      }
    }
  }
  catch (e) {
    // NOPE
  }
  finally {
    endLoading()
  }
}, 500)

function handleValueChange(_: any, option: any) {
  if (!option || !option.value) {
    return
  }

  // Check if user is already selected
  const existingUser = selectedUsers.value.find(u => u.value === option.value)
  if (existingUser) {
    return
  }

  // Add the selected user to the table
  selectedUsers.value.push({
    label: option.label,
    value: option.value,
    email: option.email,
    avatar: option.avatar,
    username: option.username,
    role: getDefaultRole(),
    alias: "",
  })

  // Clear the search input
  currentSearchValue.value = null
  handleClearOption()
}

function handleAliasChange(userId: string, alias: string) {
  const user = selectedUsers.value.find(u => u.value === userId)
  if (user) {
    user.alias = alias
  }
}

function handleRoleChange(userId: string, role: Api.Lab.LabRole) {
  const user = selectedUsers.value.find(u => u.value === userId)
  if (user) {
    user.role = role
  }
}

function handleRemoveUser(userId: string) {
  selectedUsers.value = selectedUsers.value.filter(u => u.value !== userId)
}

function handleCancel() {
  hideModal()
}

async function handleConfirm() {
  if (selectedUsers.value.length === 0) {
    message.warning("Please select at least one member")
    return
  }

  const { type, id } = props
  if (!type || !id)
    return

  startLoading()

  const response = await Promise.allSettled(
    selectedUsers.value.map(({ value, role, alias }) => {
      if (type === "lab") {
        return addLabMember(id, { userId: value, role, alias })
      }
      if (type === "project") {
        return addProjectMember({ projectId: id, userId: value, role })
      }
      if (type === "group") {
        return addGroupsMember(id, { userId: value, role })
      }
      return null
    }),
  )

  endLoading()
  const successList = response
    .map((res, idx) => (res.status === "fulfilled" && res.value?.data ? selectedUsers.value[idx] : null))
    .filter(
      (
        it,
      ): it is UserItem => Boolean(it),
    )

  if (successList.length > 0) {
    message.success(`Successfully added member ${successList.map(({ label }) => label).join(",")}`)

    emits("modal:new-member", successList.map(item => ({
      label: item.label,
      value: item.value,
      email: item.email,
      role: item.role,
    })))
    hideModal()
  }
  else {
    message.error("Failed to add members")
  }
}

function handleSetShow(val: boolean) {
  setModalStatus(val)
}

watch(
  () => isShown.value,
  (shown) => {
    if (shown) {
      emits("modal:open")
    }
    else {
      selectedUsers.value = []
      currentSearchValue.value = null
      memberOptions.value = []
      emits("modal:close")
    }
  },
)
</script>

<style scoped lang="sass">
:deep(.n-table)
  font-size: 14px

  td
    padding: 12px 16px

  th
    padding: 12px 16px
    font-weight: 600
</style>
