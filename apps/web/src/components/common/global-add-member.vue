<template>
  <n-select
    v-model:value="memberIdList"
    :size="props.size"
    :options="memberOptions"
    :render-label="renderLabel"
    :render-tag="renderMultipleSelectTag"
    :loading="loading"
    :clear-filter-after-select="true"
    :placeholder="$t('common.memberSearchPlaceholder')"
    remote
    clearable
    filterable
    multiple
    :show="isShowMenu"
    :consistent-menu-width="false"
    :theme-overrides="props.themeOverrides"
    @search="handleSearch"
    @clear="handleClear"
    @update:value="handleValueChange"
  />
</template>

<script setup lang="ts">
import { useBoolean, useLoading } from "@/composables"
import { fetchUserList } from "@/service/api/users"
import { useAuthStore } from "@/store/modules/auth"
import LabMemberTag from "@/views/labs/modules/lab-member-tag.vue"
import { $t } from "@airalogy/shared/locales"
import {
  NAvatar,
  NText,
  type SelectOption,
  type SelectProps,
  type SelectRenderLabel,
  type SelectRenderTag,
} from "naive-ui"
import { LabRole, ProjectRole } from "../../enum"

defineOptions({ name: "GlobalAddMember" })
const props = withDefaults(defineProps<IProps>(), {
  filterUser: true,
})

const emits = defineEmits<IEmits>()

export interface IProps {
  type?: "lab" | "group" | "project"
  themeOverrides?: SelectProps["themeOverrides"]
  size?: SelectProps["size"]
  filterUser?: boolean
  isPrivate?: boolean
}

export interface ICustomSelectOption {
  label: string
  value: string
  email: string
  role: Api.Lab.LabRole
  alias?: string
}
interface IEmits {
  (ev: "update:select", val: ICustomSelectOption[]): void
}

const memberIdList = ref<string[]>([])
const memberOptions = ref<SelectOption[]>([])
const selectedMembers = ref<ICustomSelectOption[]>([])

const { bool: isShowMenu, setFalse: hideMenu, setTrue: showMenu } = useBoolean()
const { loading, startLoading, endLoading } = useLoading()
const authStore = useAuthStore()

const renderMultipleSelectTag: SelectRenderTag = ({ option, handleClose }) => {
  const { label, value, avatar, username } = option
  const { type, isPrivate } = props
  return h(LabMemberTag, {
    "name": label as string,
    "username": username as string,
    "id": String(value),
    "avatar": String(avatar),
    "role": isPrivate ? ProjectRole.RECORDER : ProjectRole.EXPLORER,
    "onTag:close": () => {
      handleClose()
    },
    "onTag:select": () => {
      handleClose()
    },
    "onSelect:role": (val: { role: Api.Lab.LabRole, id: string }) => {
      const { role, id } = val
      const userIndex = selectedMembers.value.findIndex(it => it.value === id)
      if (userIndex !== -1) {
        const updatedUser = { ...selectedMembers.value[userIndex], role }
        selectedMembers.value = [
          ...selectedMembers.value.slice(0, userIndex),
          updatedUser,
          ...selectedMembers.value.slice(userIndex + 1),
        ]
      }
    },
    "onUpdate:alias": (val: { alias: string, id: string }) => {
      const { alias, id } = val
      const user = selectedMembers.value.find(it => it.value === id)
      if (user) {
        user.alias = alias
      }
    },
    "type": type,
    "changeRole": type === "lab" || type === "group" || type === "project",
    "isPrivate": isPrivate,
  })
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
                ? h(
                  NText,
                  { depth: 3, tag: "span", style: { marginLeft: "4px" } },
                  { default: () => `(@${option.username as string})` },
                )
                : null,
            ],
          }),
          h(
            NText,
            { depth: 3, tag: "div" },
            {
              default: () => option.email as string,
            },
          ),
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
  memberIdList.value = []
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
        // Determine default role based on type and privacy settings
        let defaultRole: Api.Lab.LabRole
        if (props.type === "lab" || props.type === "group") {
          defaultRole = LabRole.MEMBER
        }
        else if (props.type === "project") {
          defaultRole = props.isPrivate ? ProjectRole.RECORDER : ProjectRole.COLLABORATOR
        }
        else {
          defaultRole = ProjectRole.EXPLORER
        }

        memberOptions.value = data
          .filter(({ id }) => props.filterUser ? id !== userId : true)
          .map(
            ({ name, username, id, email, avatar_url }): SelectOption => ({
              label: name || username,
              username,
              value: id,
              email,
              role: defaultRole,
              avatar: avatar_url,
            }),
          )
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

const handleValueChange: SelectProps["onUpdate:value"] = (
  _,
  option: { label: string, value: string, email: string, role: Api.Lab.LabRole }[],
) => {
  selectedMembers.value = option
  handleClearOption()
}

watch(
  () => selectedMembers.value,
  () => {
    emits("update:select", selectedMembers.value)
  },
)
</script>
