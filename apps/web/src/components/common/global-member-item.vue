<template>
  <div class="h-full" :class="[props.isCompact ? 'max-w-30' : 'min-w-20']">
    <span class="relative">
      <n-popover
        trigger="hover"
        placement="top-start"
        :show-arrow="false"
        :disabled="!enableHoverCard"
      >
        <template #trigger>
          <router-link :to="userRoute" class="!hover:router-link">
            <span v-if="showAtSymbol">@</span>
            <template v-if="showAlias">
              <span>{{ displayAlias }}</span>
              <span v-if="baseName" class="text-xs"> ({{ baseName }}) </span>
            </template>
            <span v-else>{{ baseName }}</span>
          </router-link>
        </template>
        <div class="user-hover-card">
          <div class="flex items-center gap-3">
            <n-avatar
              :src="avatarUrl"
              size="small"
              class="shrink-0"
              fallback-src="/images/avatar_default.svg"
              color="transparent"
              object-fit="cover"
            />
            <div class="min-w-0">
              <div class="truncate text-sm font-medium text-gray-900">
                {{ displayAlias || baseName || item.username }}
              </div>
              <div v-if="item.username" class="text-xs text-gray-500">
                @{{ item.username }}
              </div>
              <div v-if="showAlias && baseName" class="text-xs text-gray-400">
                {{ baseName }}
              </div>
            </div>
          </div>
          <div v-if="canSetUserAlias" class="mt-2">
            <n-button size="tiny" quaternary @click.stop="openUserAliasDialog">
              {{ $t("common.setUserAlias") }}
            </n-button>
          </div>
        </div>
      </n-popover>
      <span v-if="(item as Api.Project.MemberListItem).group_name" class="ml-2 text-xs">
        ({{ (item as Api.Project.MemberListItem).group_name }})
      </span>
      <global-role-tag v-bind="props" :class="[!props.isCompact && 'ml-5']" />
    </span>
  </div>
</template>

<script setup lang="ts">
import type { RouteLocationRaw } from "vue-router"
import { setUserAlias } from "@/service/api/users"
import { useAuthStore } from "@/store/modules/auth"
import UpdateAliasModal from "@/views/labs/modules/lab/UpdateAliasModal.vue"
import { useClosableMessage } from "@airalogy/composables"
import { $t } from "@airalogy/shared/locales"
import { useDialog } from "naive-ui"
import { ProjectType } from "../../enum"

export interface IProps {
  item: Api.Lab.MemberListItem | Api.Project.MemberListItem | Api.Groups.MemberListItem | Api.Profile.User | { name: string, username: string, avatar_url: string, alias?: string, id: string, user_alias?: string, lab_alias?: string }
  type: "lab" | "group" | "project"
  isCompact?: boolean
  showAtSymbol?: boolean
  isOwner?: boolean
  projectType?: ProjectType
  enableHoverCard?: boolean
}

const props = withDefaults(defineProps<IProps>(), {
  isCompact: true,
  showAtSymbol: false,
  projectType: ProjectType.PUBLIC,
  enableHoverCard: true,
})

const authStore = useAuthStore()
const dialog = useDialog()
const message = useClosableMessage()
const localUserAlias = ref<string | undefined>(undefined)

const baseName = computed(() => props.item.name || props.item.username || "")
const avatarUrl = computed(() => {
  const item = props.item as Api.Profile.User
  return item.avatar_url || item.avatar || "/images/avatar_default.svg"
})

const userAlias = computed(() => {
  if (localUserAlias.value !== undefined) {
    return localUserAlias.value
  }
  return props.item.user_alias || ""
})

const displayAlias = computed(() => {
  const item = props.item as Api.Lab.MemberListItem & { alias?: string }
  return userAlias.value || item.lab_alias || item.alias || ""
})

const showAlias = computed(() => {
  if (!displayAlias.value)
    return false

  return displayAlias.value !== baseName.value
})

const canSetUserAlias = computed(() => {
  const currentUserId = authStore.userInfo?.id
  return Boolean(currentUserId && props.item?.id && props.item.id !== currentUserId)
})

const userRoute = computed(
  (): RouteLocationRaw => ({
    name: "user-profile",
    params: { username: props.item.username },
  }),
)

function openUserAliasDialog() {
  if (!canSetUserAlias.value) {
    return
  }

  const aliasRef = ref<InstanceType<typeof UpdateAliasModal>>()
  const dialogInstance = dialog.info({
    title: $t("common.setUserAlias"),
    content: () =>
      h(UpdateAliasModal, {
        ref: aliasRef,
        alias: userAlias.value,
        label: $t("common.userAliasLabel"),
        placeholder: $t("common.userAliasPlaceholder"),
        requiredMessage: $t("common.userAliasRequired"),
        required: false,
      }),
    positiveText: $t("common.confirm"),
    negativeText: $t("common.cancel"),
    showIcon: false,
    onPositiveClick: async () => {
      dialogInstance.loading = true
      try {
        const alias = await aliasRef.value?.getAlias()
        const trimmedAlias = (alias as string || "").trim()
        await setUserAlias({ target_user_id: props.item.id, alias: trimmedAlias })
        localUserAlias.value = trimmedAlias
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
</script>

<style scoped lang="sass">
.user-hover-card
  min-width: 220px
  max-width: 260px
  padding: 8px
  color: #1f2937
</style>
