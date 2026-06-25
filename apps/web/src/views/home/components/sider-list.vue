<template>
  <div class="relative">
    <div class="px-5">
      <div class="list__title ml-4">
        <router-link :to="route" class="hover:router-link">
          {{ props.title }}
        </router-link>
      </div>
      <n-divider />
    </div>
    <n-spin :show="loading" class="min-h-20 w-full">
      <div
        v-if="listItems.length > 0"
        class="sider-list relative opacity-0 transition-opacity-200 transition-delay-100"
        :class="listItems.length > 0 && 'opacity-100'"
      >
        <div v-for="(item, idx) in listItems" :key="getItemKey(item, idx)" class="sider-row group">
          <div class="sider-icon">
            <n-avatar
              v-if="props.type === 'lab' && (item as Api.Lab.LabInfo).logo_url"
              :src="(item as Api.Lab.LabInfo).logo_url || undefined"
              :size="40"
              color="transparent"
              object-fit="cover"
            />
            <lab-icon v-else-if="props.type === 'lab'" />
            <project-icon v-else-if="props.type === 'project'" />
            <research-icon v-else />
          </div>
          <sider-item
            :type="props.type"
            :item="item"
            class="sider-content"
            :style="{ width: `${props.width}px` }"
          />
          <n-tooltip v-if="showPin" placement="top">
            <template #trigger>
              <n-button
                quaternary
                size="small"
                class="pin-action"
                :class="{ 'pin-action--active': isPinning(item) }"
                :loading="isPinning(item)"
                @click.stop="handleTogglePin(item, $event)"
              >
                <n-icon
                  :component="PinnedIcon"
                  :size="16"
                  :color="isPinned(item) ? '#0084E2' : '#A1A4AF'"
                />
              </n-button>
            </template>
            {{ isPinned(item) ? $t("icon.unpin") : $t("icon.pin") }}
          </n-tooltip>
        </div>
      </div>
      <div v-else-if="!loading" class="mt-2.5 h-25 px-10 text-center text-xl leading-25 opacity-30">
        {{ $t("page.home.placeholder") }}
      </div>
    </n-spin>
  </div>
</template>

<script setup lang="ts">
import type { ProtocolModels } from "@airalogy/shared/types"
import type { RouteLocationRaw } from "vue-router"
import LabIcon from "@/components/icon/lab-icon.vue"
import ProjectIcon from "@/components/icon/project-icon.vue"
import ResearchIcon from "@/components/icon/protocol-icon.vue"
import { type PinnedItem, PinnedResourceType } from "@/service/api/pinned-items"
import { fetchUserLabs, fetchUserProjects, fetchUserProtocols } from "@/service/api/users"

import { useAuthStore } from "@/store/modules/auth"
import { useClosableMessage, useLoading } from "@airalogy/composables"
import { $t } from "@airalogy/shared/locales"
import PinnedIcon from "~icons/tabler/pinned"
import { NAvatar } from "naive-ui"

import SiderItem, { type IProps as ISiderItemProps } from "./sider-item.vue"

export interface IProps {
  title?: string
  type: ISiderItemProps["type"]
  width?: number
  pinnedMap?: Map<string, PinnedItem>
  pinningKeys?: Set<string>
}
export type IListItem = Api.Lab.LabInfo | ProtocolModels.ProjectProtocolInfo | Api.Project.MyProjectInfo
const props = withDefaults(defineProps<IProps>(), {
  title: "",
  type: "protocol",
  width: 398,
})

const emits = defineEmits<IEmits>()
interface IEmits {
  (ev: "update:list", type: ISiderItemProps["type"], info: IListItem[]): void
  (ev: "togglePin", payload: { resourceType: PinnedResourceType, resourceId: string }): void
}
const message = useClosableMessage()

const info = ref<Api.GetResponse<IListItem>>({
  total_count: 0,
  data: [],
})

const authStore = useAuthStore()

const route = computed((): RouteLocationRaw => {
  const { type } = props
  if (type === "protocol") {
    return { name: "protocols-my" }
  }
  if (type === "lab") {
    return { name: "labs" }
  }
  if (type === "project") {
    return { name: "project-dashboard" }
  }

  return { name: "not-found" }
})
const { endLoading, loading, startLoading } = useLoading(true)

const showPin = computed(() => Boolean(props.pinnedMap))
const resourceTypeMap: Record<ISiderItemProps["type"], PinnedResourceType> = {
  lab: PinnedResourceType.Lab,
  project: PinnedResourceType.Project,
  protocol: PinnedResourceType.Protocol,
}

function getPinnedKey(item: IListItem) {
  const id = (item as { id?: string }).id
  if (!id) {
    return null
  }
  return `${resourceTypeMap[props.type]}:${id}`
}

function isPinned(item: IListItem) {
  const key = getPinnedKey(item)
  if (!key || !props.pinnedMap) {
    return false
  }
  return props.pinnedMap.has(key)
}

function isPinning(item: IListItem) {
  const key = getPinnedKey(item)
  if (!key || !props.pinningKeys) {
    return false
  }
  return props.pinningKeys.has(key)
}

function handleTogglePin(item: IListItem, event: MouseEvent) {
  event.preventDefault()
  event.stopPropagation()
  const id = (item as { id?: string }).id
  if (!id) {
    return
  }
  emits("togglePin", { resourceType: resourceTypeMap[props.type], resourceId: id })
}

async function fetchList() {
  const { userInfo } = authStore
  const { type } = props

  if (!userInfo || !userInfo.id) {
    message.error("Authentication required")
    return
  }

  const { id: userId } = userInfo
  startLoading()
  try {
    // TODO: recent experiment API
    if (type === "protocol") {
      const data = await fetchUserProtocols(userId, { page: 1, pageSize: 5, sortedBy: "updated_at" })
      if (data) {
        await nextTick(() => {
          emits("update:list", "protocol", data.protocols)
          info.value = {
            data: data.protocols,
            total_count: data.total_count,
          }
        })
      }
      endLoading()
      return
    }

    if (type === "lab") {
      const data = await fetchUserLabs(userId, { page: 1, pageSize: 5, sortedBy: "updated_at" })
      if (data) {
        await nextTick(() => {
          info.value = {
            data: data.labs,
            total_count: data.total_count,
          }

          emits("update:list", props.type, data.labs)
        })
      }
    }

    if (type === "project") {
      const data = await fetchUserProjects(userId, { page: 1, pageSize: 5, sortedBy: "updated_at" })
      if (data) {
        await nextTick(() => {
          info.value = {
            data: data.projects,
            total_count: data.projects.length,
          }

          emits("update:list", props.type, data.projects)
        })
      }
    }
  }
  catch (err) {
  }
  finally {
    endLoading()
  }
}

const listItems = computed<IListItem[]>(() => {
  const { data } = info.value
  if (Array.isArray(data)) {
    return data.slice(0, 100)
  }
  return []
})

function getItemKey(item: IListItem, idx: number) {
  const candidate = (item as { id?: string }).id
  return candidate || `${props.type}-${idx}`
}

onMounted(async () => {
  await fetchList()
})
</script>

<style scoped lang="sass">
@use "@styles/sass/list.sass" as *

:deep(.n-divider)
  margin: 1rem 0 0!important

.sider-list
  display: flex
  flex-direction: column
  gap: 4px
  padding: 0 12px 12px

.sider-row
  display: flex
  align-items: center
  gap: 8px
  padding: 8px 12px
  border-radius: 12px
  transition: background-color .2s ease

.sider-row:hover
  background: #F5F6F8

.sider-icon
  width: 40px
  height: 40px
  display: flex
  align-items: center
  justify-content: center

.sider-content
  flex: 1

.pin-action
  opacity: 0
  transition: opacity .2s ease

.sider-row:hover .pin-action
  opacity: 1

.pin-action--active
  opacity: 1
</style>
