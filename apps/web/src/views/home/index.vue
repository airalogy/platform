<template>
  <n-layout has-sider class="my-12.5 overflow-visible" :content-class="isMobile ? '!flex-col' : ''">
    <n-layout-sider :content-class="['!overflow-visible', isMobile ? 'items-center' : ''].join(' ')" :width="isMobile ? '100%' : 398">
      <div class="n-card n-card--bordered rounded-2 pt-6">
        <sider-list
          :title="$t('page.home.labs')"
          type="lab"
          :width="isMobile ? width - 100 : 300"
          :pinned-map="pinnedMap"
          :pinning-keys="pinningKeys"
          @togglePin="handleTogglePin"
        />
        <n-divider style="margin: 1rem 0 !important" />
        <sider-list
          :title="$t('page.home.projects')"
          type="project"
          :width="isMobile ? width - 100 : 300"
          :pinned-map="pinnedMap"
          :pinning-keys="pinningKeys"
          @togglePin="handleTogglePin"
        />
        <n-divider style="margin: 1rem 0 !important" />
        <sider-list
          :title="$t('page.home.recentProtocols')"
          type="protocol"
          :width="isMobile ? width - 100 : 300"
          :pinned-map="pinnedMap"
          :pinning-keys="pinningKeys"
          @togglePin="handleTogglePin"
        />
      </div>
    </n-layout-sider>
    <n-layout>
      <n-layout-content class="!overflow-visible" :content-class="isMobile ? 'px-4' : 'ml-6'">
        <section class="mb-6 rounded-2 border border-gray-200 bg-white p-5">
          <div class="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div class="max-w-2xl">
              <div class="text-xs font-medium uppercase text-gray-500">
                {{ $t("page.home.start.eyebrow") }}
              </div>
              <h2 class="mb-0 mt-2 text-2xl font-semibold leading-tight">
                {{ $t("page.home.start.title") }}
              </h2>
              <p class="mb-0 mt-2 text-sm leading-6 text-gray-500">
                {{ $t("page.home.start.description") }}
              </p>
            </div>
            <div class="flex flex-wrap gap-2">
              <create-project-modal
                :button-props="{ type: 'primary' }"
                :show-icon="false"
                :trigger="$t('page.home.start.primaryAction')"
                @modal:new-project="handleCreateProject"
              />
              <n-button secondary @click="handleOpenHub">
                {{ $t("page.home.start.hubAction") }}
              </n-button>
            </div>
          </div>
          <div class="mt-5 grid grid-cols-1 gap-3 md:grid-cols-3">
            <div
              v-for="step in gettingStartedSteps"
              :key="step.key"
              class="rounded border border-gray-200 bg-gray-50 px-4 py-3"
            >
              <div class="text-sm font-semibold">
                {{ step.title }}
              </div>
              <div class="mt-1 text-sm leading-6 text-gray-500">
                {{ step.description }}
              </div>
            </div>
          </div>
        </section>
        <pinned-items
          class="mb-6"
          :items="pinnedItems"
          :loading="pinnedLoading"
          :pinning-keys="pinningKeys"
          :max-count="maxPinnedCount"
          @togglePin="handleTogglePin"
          @reorderPinned="handleReorderPinned"
        />
      </n-layout-content>
      <n-layout-header v-if="totalCount > 0 || !loading">
        <h3 class="px-6 pb-3 pt-6 text-[18px] font-medium">
          {{ $t("page.home.activities") }}
        </h3>
      </n-layout-header>
      <n-layout-content
        :content-class="
          loading || totalCount > 0 ? '!pb-10 !overflow-visible' : '!overflow-visible'
        "
        class="!overflow-visible"
      >
        <n-spin :show="loading" class="min-h-40" :content-class="isMobile ? 'px-4' : 'ml-6'">
          <template v-if="loading || totalCount > 0">
            <activity-card
              v-for="item in activityList"
              :key="item.id"
              v-bind="item"
              :loading="loading && totalCount === 0"
            />
            <n-button
              v-if="hasMore"
              :loading="loading"
              type="default"
              size="large"
              class="mt-4 w-full"
              @click="handleLoadMore"
            >
              {{ $t("page.home.loadMore") }}
            </n-button>
          </template>
          <n-card
            v-else
            bordered
            class="flex items-center justify-center px-20 py-24.5"
            header-class="!text-8 text-center "
            content-class="!text-4"
          >
            <template #header>
              {{
                $t("page.home.empty.title", {
                  name: authStore.userInfo.name || authStore.userInfo.username,
                })
              }}
            </template>
            <p class="mb-4">
              {{ $t("page.home.empty.description") }}
            </p>
            <div class="flex flex-wrap items-center justify-center gap-2">
              <create-lab-modal
                :button-props="{ type: 'primary', ghost: false, text: false }"
                :trigger="$t('page.home.empty.createLabAction')"
                @modal:new-lab="handleCreateLab"
              />
              <n-button secondary @click="handleOpenHub">
                {{ $t("page.home.empty.hubAction") }}
              </n-button>
            </div>
          </n-card>
        </n-spin>
      </n-layout-content>
    </n-layout>

    <!-- Testing Notification Dialog for New Users -->
    <testing-notification-dialog
      v-model:show="showTestingDialog"
      @get-started="handleGetStarted"
      @dismiss="handleDismissDialog"
    />
  </n-layout>
</template>

<script setup lang="ts">
import { useRouterPush } from "@/composables/useRouterPush"
import { getActivities } from "@/service/api/activities"
import { createPinnedItem, deletePinnedItem, getPinnedItems, type PinnedItem, PinnedResourceType, reorderPinnedItems } from "@/service/api/pinned-items"
import { getProtocolInfo } from "@/service/api/protocol"

import { useAppStore } from "@/store/modules/app"
import { useAuthStore } from "@/store/modules/auth"
import TestingNotificationDialog from "@/views/auth/components/testing-notification-dialog.vue"
import CreateLabModal from "@/views/labs/modules/lab/create-lab-modal.vue"
import CreateProjectModal from "@/views/projects/modules/create-project-modal.vue"

import { useClosableMessage, useLoading } from "@airalogy/composables"
import { useBasicLayout } from "@airalogy/composables/useBasicLayout"
import { $t } from "@airalogy/shared/locales"
import { useWindowSize } from "@vueuse/core"
import ActivityCard, { type IProps as ICardItem } from "./components/activity-card.vue"
import PinnedItems from "./components/pinned-items.vue"
import SiderList from "./components/sider-list.vue"

const authStore = useAuthStore()
const { loading, startLoading, endLoading } = useLoading()
const { loading: pinnedLoading, startLoading: startPinnedLoading, endLoading: endPinnedLoading } = useLoading(true)
const message = useClosableMessage()

const activityRecord = ref<
  Record<"records" | "labs" | "projects" | "groups", Api.Activity.ActivityItem[]>
>({
  records: [],
  labs: [],
  projects: [],
  groups: [],
})
const totalCount = computed(() =>
  Object.values(activityRecord.value).reduce((acc, curr) => acc + curr.length, 0),
)

const currentPage = ref(1)
const pageSize = ref(5)
const hasMore = ref(true)
const { isMobile, breakpoints } = useBasicLayout()
const { width } = useWindowSize()

const maxPinnedCount = 10
const pinnedItems = ref<PinnedItem[]>([])
const pinningKeys = ref(new Set<string>())

const pinnedMap = computed(() => {
  const map = new Map<string, PinnedItem>()
  pinnedItems.value.forEach((item) => {
    map.set(`${item.resource_type}:${item.resource_id}`, item)
  })
  return map
})

const gettingStartedSteps = computed(() => [
  {
    key: "workspace",
    title: $t("page.home.start.steps.workspace.title"),
    description: $t("page.home.start.steps.workspace.description"),
  },
  {
    key: "protocol",
    title: $t("page.home.start.steps.protocol.title"),
    description: $t("page.home.start.steps.protocol.description"),
  },
  {
    key: "record",
    title: $t("page.home.start.steps.record.title"),
    description: $t("page.home.start.steps.record.description"),
  },
])

type ActivityCategory = "projects" | "labs" | "records" | "protocols" | "groups"

function getLocalizedActivityAction(action: string) {
  const normalizedAction = action.trim().toLowerCase()

  switch (normalizedAction) {
    case "added":
      return $t("page.home.activityAction.added")
    case "created":
      return $t("page.home.activityAction.created")
    case "updated":
      return $t("page.home.activityAction.updated")
    case "deleted":
      return $t("page.home.activityAction.deleted")
    case "joined":
      return $t("page.home.activityAction.joined")
    case "left":
      return $t("page.home.activityAction.left")
    default:
      return action
  }
}

function getActivityText(key: ActivityCategory, action: string) {
  switch (key) {
    case "projects":
      return $t("page.home.activityText.project", {
        action: getLocalizedActivityAction(action),
      })
    case "labs":
      return $t("page.home.activityText.lab", {
        action: getLocalizedActivityAction(action),
      })
    case "records":
      return $t("page.home.activityText.record")
    case "protocols":
      return $t("page.home.activityText.protocol")
    case "groups":
      return $t("page.home.activityText.group", {
        action: getLocalizedActivityAction(action),
      })
    default:
      return action
  }
}

const activityList = computed((): ICardItem[] => {
  const entries = Object.entries(activityRecord.value)
  const list = entries
    .map(([key, val]) =>
      val.map((it): ICardItem => {
        const {
          lab,
          project,
          record,
          group,
          node,
          action,
          created_at,
          id,
          description,
          uid,
          name,
          protocol,
        } = it

        const activity = getActivityText(key as ActivityCategory, action)

        return {
          activity,
          project: key === "projects" ? { id, uid, name } : project,
          lab: key === "labs" ? { id, uid, name } : lab,
          record,
          protocol,
          group,
          node,
          time: created_at,
          id: `${key}-${id}`,
          user: authStore.userInfo,
          description,
        }
      }),
    )
    .flat()

  return list.sort((a, b) => new Date(b.time).getTime() - new Date(a.time).getTime())
})

async function handleLoadMore() {
  currentPage.value++
  await fetchData({
    currentPage: currentPage.value,
    currentPageSize: pageSize.value,
    isLoadMore: true,
  })
}

async function fetchData({
  currentPage: currPage,
  currentPageSize: currSize,
  isLoadMore = false,
}: {
  currentPage: number
  currentPageSize: number
  isLoadMore?: boolean
}) {
  try {
    startLoading()

    const { data, error } = await getActivities({
      userId: authStore.userInfo.id,
      page: currPage,
      pageSize: currSize,
    })

    if (data) {
      // If loading more, append to existing data
      if (isLoadMore) {
        Object.keys(data).forEach((key) => {
          const typedKey = key as keyof typeof activityRecord.value
          activityRecord.value[typedKey] = [...activityRecord.value[typedKey], ...data[typedKey]]
        })
      }
      else {
        activityRecord.value = data
      }

      // Check if we have more data to load
      const newItemsCount = Object.values(data).reduce((acc, curr) => acc + curr.length, 0)
      hasMore.value = newItemsCount === currSize
    }
    else if (error) {
      if (isLoadMore)
        currentPage.value--
    }
  }
  catch (error) {
    if (isLoadMore)
      currentPage.value--
  }
  finally {
    endLoading()
  }
}

async function fetchPinnedItems() {
  startPinnedLoading()
  try {
    const { data, error } = await getPinnedItems()
    if (data) {
      const items = data.items || []
      const protocolItems = items.filter(item => item.resource_type === PinnedResourceType.Protocol)
      if (protocolItems.length > 0) {
        const results = await Promise.allSettled(
          protocolItems.map(item => getProtocolInfo(item.resource_id)),
        )
        results.forEach((result, index) => {
          if (result.status === "fulfilled" && result.value.data) {
            protocolItems[index]!.resource = result.value.data
          }
        })
      }
      pinnedItems.value = items
    }
    else if (error) {
      message.error("Failed to load pinned items")
    }
  }
  catch {
    message.error("Failed to load pinned items")
  }
  finally {
    endPinnedLoading()
  }
}

async function handleTogglePin(payload: { resourceType: PinnedResourceType, resourceId: string }) {
  const { resourceType, resourceId } = payload
  if (!resourceId) {
    return
  }

  const key = `${resourceType}:${resourceId}`
  if (pinningKeys.value.has(key)) {
    return
  }

  pinningKeys.value.add(key)
  try {
    const existing = pinnedMap.value.get(key)
    if (existing) {
      await deletePinnedItem(existing.id)
    }
    else {
      await createPinnedItem({ resource_type: resourceType, resource_id: resourceId })
    }
    await fetchPinnedItems()
  }
  finally {
    pinningKeys.value.delete(key)
  }
}

async function handleReorderPinned(pinnedItemIds: number[]) {
  if (!Array.isArray(pinnedItemIds) || pinnedItemIds.length === 0) {
    return
  }

  const itemMap = new Map(pinnedItems.value.map(item => [item.id, item]))
  const nextItems = pinnedItemIds.map(id => itemMap.get(id)).filter(Boolean) as PinnedItem[]
  if (nextItems.length > 0) {
    pinnedItems.value = nextItems
  }

  try {
    await reorderPinnedItems(pinnedItemIds)
  }
  catch {
    message.error("Failed to reorder pinned items")
    await fetchPinnedItems()
  }
}

const appStore = useAppStore()
const { routerPushByKey } = useRouterPush()

// Testing notification dialog state
const showTestingDialog = ref(false)
const hasShownTestingDialog = ref(false)

async function handleCreateLab(item: Api.Lab.LabInfo) {
  const { uid } = item

  await routerPushByKey("lab-projects", { params: { labUid: uid } })
}

async function handleCreateProject(item: Api.Project.MyProjectInfo) {
  await routerPushByKey("project-protocols", {
    params: {
      labUid: item.lab_uid,
      projectUid: item.uid,
    },
  })
}

function handleOpenHub() {
  void routerPushByKey("hub")
}

// Handle testing dialog actions
function handleGetStarted() {
  // Clear the signup flag and allow natural navigation
  authStore.clearSignupFlag()
  hasShownTestingDialog.value = true
}

function handleDismissDialog() {
  // Clear the signup flag and allow natural navigation
  authStore.clearSignupFlag()
  hasShownTestingDialog.value = true
}

onMounted(async () => {
  await Promise.all([
    fetchPinnedItems(),
    fetchData({ currentPage: currentPage.value, currentPageSize: pageSize.value }),
  ])
})

// Also watch for auth state changes in case user navigates between pages
watch(() => authStore.justSignedUp, (newValue) => {
  if (newValue && !hasShownTestingDialog.value && !loading.value) {
    showTestingDialog.value = true
    hasShownTestingDialog.value = true
  }
}, { immediate: true })
</script>

<style scoped lang="sass">
:deep(.n-layout-scroll-container)
  overflow-x: visible!important
</style>
