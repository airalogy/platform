<template>
  <div class="size-full">
    <define-summary-item v-slot="{ count, label }">
      <div
        class="min-w-[120px] flex flex-col items-center rounded text-xl font-semibold transition-colors hover:bg-gray-50"
      >
        <!-- <n-number-animation :from="0" :to="count" /> -->
        <div>{{ count }}</div>
        <div class="mt-2 text-sm text-gray-600 font-normal">
          {{ label }}
        </div>
      </div>
    </define-summary-item>

    <define-wrapper-item v-slot="{ $slots, title, handleViewAll, contentClass, showViewAll }">
      <div class="mb-4">
        <div class="mb-4 flex items-center gap-2 text-lg font-medium">
          {{ title }}
          <n-button
            v-if="showViewAll && handleViewAll"
            quaternary
            icon-placement="right"
            size="small"
            class="ml-1"
            @click="handleViewAll"
          >
            View All
            <template #icon>
              <n-icon size="12">
                <icon-ion-ios-arrow-forward />
              </n-icon>
            </template>
          </n-button>
        </div>
        <n-card class="w-full" size="small" :content-class="contentClass || '!p-1' ">
          <component :is="$slots.default" />
        </n-card>
      </div>
    </define-wrapper-item>

    <div class="size-full" v-bind="$attrs">
      <wrapper-item title="Overview" content-class="!p-4">
        <div class="flex flex-wrap justify-center gap-2 sm:justify-start">
          <summary-item v-for="key in countKey" :key="key" v-bind="countRecord[key]" />
        </div>
      </wrapper-item>

      <wrapper-item
        v-if="userLabCount > 0 && userLabList.length > 0"
        title="Labs"
        :handle-view-all="handleViewAllLabs"
        :show-view-all="viewAllState.lab === true"
      >
        <lab-list :list="viewAllState.lab ? userLabList.slice(0, 5) : userLabList " :show-actions="false" :show-private="showPrivate" />
      </wrapper-item>

      <wrapper-item
        v-if="userGroupCount > 0 && userGroupList.length > 0"
        title="Groups"
        :handle-view-all="handleViewAllGroups"
        :show-view-all="viewAllState.group === true"
      >
        <lab-group-list :list="viewAllState.group ? userGroupList.slice(0, 5) : userGroupList" :show-actions="false" :show-private="showPrivate" />
      </wrapper-item>

      <wrapper-item
        v-if="userProjectCount > 0 && userProjectList.length > 0"
        title="Projects"
        :handle-view-all="handleViewAllProjects"
        :show-view-all="viewAllState.project === true"
      >
        <project-list :list="viewAllState.project ? userProjectList.slice(0, 5) : userProjectList" :show-actions="false" :show-private="showPrivate" />
      </wrapper-item>

      <wrapper-item
        v-if="userProtocolCount > 0 && userProtocolList.length > 0"
        title="Protocols"
        :handle-view-all="handleViewAllProtocols"
        :show-view-all="viewAllState.protocol === true"
      >
        <project-protocol-list :list="viewAllState.protocol ? userProtocolList.slice(0, 5) : userProtocolList" :show-actions="false" :show-private="showPrivate" />
      </wrapper-item>
    </div>
  </div>
</template>

<script lang="ts" setup>
import { useAuthStore } from "@/store/modules/auth"
import LabGroupList from "@/views/labs/modules/group/lab-group-list.vue"
import LabList from "@/views/labs/modules/lab/lab-list.vue"
import ProjectProtocolList from "@/views/project/modules/project-protocol-list.vue"
import ProjectList from "@/views/projects/modules/project-list.vue"
import { useProfileStore } from "../hooks/useProfileStore"

defineOptions({ name: "ProfileSummary", inheritAttrs: false })

interface SummaryItemProps {
  count: number
  label: string
}

const [DefineSummaryItem, SummaryItem] = createReusableTemplate<SummaryItemProps>()
const [DefineWrapperItem, WrapperItem] = createReusableTemplate<{
  title: string
  handleViewAll?: () => void
  contentClass?: string
  showViewAll?: boolean
}>()

const countKey = ["labs", "projects", "protocols", "groups"] as const
type CountKey = (typeof countKey)[number]
const {
  userLabCount,
  userProjectCount,
  userProtocolCount,
  userGroupCount,
  fetchUserLabsData,
  fetchUserProjectsData,
  fetchUserProtocolsData,
  fetchUserGroupsData,
  userInfo,
  userLabList,
  userProjectList,
  userProtocolList,
  userGroupList,
  viewAllState,
} = useProfileStore()!
const authStore = useAuthStore()

const showPrivate = computed(() => {
  if (authStore.userInfo.id === userInfo.value?.id) {
    return true
  }

  return false
})

const countRecord = computed<Record<CountKey, SummaryItemProps>>(() => ({
  labs: { count: userLabCount.value, label: "Labs" },
  projects: { count: userProjectCount.value, label: "Projects" },
  protocols: { count: userProtocolCount.value, label: "Protocols" },
  groups: { count: userGroupCount.value, label: "Groups" },
}))

async function handleViewAllLabs() {
  const id = userInfo.value?.id
  if (!id) {
    return
  }

  await fetchUserLabsData(id, { page: 1, pageSize: 9999 })
  viewAllState.lab = false
}

async function handleViewAllProjects() {
  const id = userInfo.value?.id
  if (!id) {
    return
  }

  await fetchUserProjectsData(id, { page: 1, pageSize: 9999 })
  viewAllState.project = false
}

async function handleViewAllProtocols() {
  const id = userInfo.value?.id
  if (!id) {
    return
  }

  await fetchUserProtocolsData(id, { page: 1, pageSize: 9999 })
  viewAllState.protocol = false
}

async function handleViewAllGroups() {
  const id = userInfo.value?.id
  if (!id) {
    return
  }

  await fetchUserGroupsData(id, { page: 1, pageSize: 9999 })
  viewAllState.group = false
}

watch(
  () => userInfo.value?.id,
  async (id) => {
    if (id) {
      await Promise.all([
        fetchUserLabsData(id),
        fetchUserProjectsData(id),
        fetchUserProtocolsData(id),
        fetchUserGroupsData(id),
      ])
    }
  },
  { immediate: true },
)
</script>

<style lang="sass" scoped></style>
