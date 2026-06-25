<template>
  <global-layout>
    <content-layout v-if="tabs.length > 0" :tabs="tabs" :title="title">
      <template v-if="canManageLab || canManageGroup " #suffix>
        <add-project-modal
          v-if="route.name === 'lab-group-projects' && groupInfo && canManageGroup" :id="groupInfo.id"
          :lab-info="labInfo" @modal:new-project="handleCreateProject"
        />
        <global-add-member-table-modal
          v-if="route.name === 'lab-group-members' && canManageLab" :id="String(groupInfo?.id)" show-icon
          :trigger="$t('common.addMember')" type="group" @modal:new-member="handleNewMember"
        />
      </template>
      <template #title>
        <div class="mt-5 flex items-center">
          <role-icon type="group" />
          <template v-if="groupInfo">
            <router-link
              :to="{ name: 'lab-projects', params: { labUid: groupInfo?.lab_uid } }"
              class="ml-5 inline-block max-w-[300px] ellipsis-text text-6 color-text-secondary !hover:router-link"
            >
              {{ labName }}
            </router-link>
            <span class="mx-3 select-none text-5 color-text-secondary">/</span>
            <h2 class="inline-block max-w-[300px] ellipsis-text !text-6">
              {{ groupTitle }}
            </h2>
            <lock-icon v-if="groupInfo.type === 1" class="ml-3" />
          </template>
          <n-skeleton v-else width="20rem" class="mx-4" />
          <!-- <edit-group-modal :item="groupInfo" @modal:edit-group="handleEditGroup" /> -->
        </div>
        <global-description
          v-if="description"
          :description="description"
          :show-button="showButton"
          :show-full-content="showFullContent"
          @toggle="toggle"
        />
      </template>
    </content-layout>
    <div v-else class="w-full flex-center">
      <img src="/images/project_placeholder.png" alt="" class="h-[988px] object-contain">
    </div>
  </global-layout>
</template>

<script setup lang="ts">
import type { SelectOption } from "naive-ui"
import GlobalAddMemberTableModal from "@/components/common/global-add-member-table-modal.vue"
import GlobalDescription from "@/components/common/global-description.vue"
import { useBoolean } from "@/composables"

import { useRouterPush } from "@/composables/useRouterPush"
import ContentLayout from "@/layouts/content-layout/index.vue"
import GlobalLayout from "@/layouts/global-layout/index.vue"

import { useAppStore } from "@/store/modules/app"
import { useAuthStore } from "@/store/modules/auth"

import { useRouteStore } from "@/store/modules/route"
import { useProvideLabInfoStore } from "@/views/labs/hooks/useLabsInfoStore"
import { $t } from "@airalogy/shared/locales"
import { useLabPermissions } from "../../composables/useLabPermissions"

import { useProvideGroupInfoStore } from "./hooks/useGroupInfoStore"
import AddProjectModal from "./modules/add-project-modal.vue"

defineOptions({
  name: "LabLayout",
})

withDefaults(defineProps<Props>(), {
  showPadding: false,
})

interface Props {
  /** Show padding for content */
  showPadding?: boolean
}

const routerStore = useRouteStore()
const authStore = useAuthStore()

const route = useRoute()

const { routerPushByKey } = useRouterPush()
const { fetchLabInfoByUid, labInfo, isManager } = useProvideLabInfoStore(null)
const { fetchGroupInfo, groupInfo } = useProvideGroupInfoStore(null)
const { canManageGroup, canManageLab } = useLabPermissions(labInfo)

const baseTabs = [
  { name: "lab-group-projects", tab: $t("page.group.projects") },
  { name: "lab-group-members", tab: $t("page.group.members") },
]
const tabs = computed(() => {
  if (isManager.value) {
    return baseTabs.concat({ name: "lab-group-settings", tab: $t("page.group.settings") })
  }

  return baseTabs
})

const title = computed(() => {
  const { name } = route

  if (name === "labs-my" || name === "labs-public") {
    return "Labs"
  }

  if (name === "lab-projects" || name === "lab-members" || name === "lab-groups") {
    const { name: labName, uid } = labInfo.value || {}

    return labName || uid || "Labs"
  }

  return "Labs"
})

const description = computed(() => {
  return labInfo.value?.description ?? ""
})
const showButton = computed(() => description.value.length > 1000)

const { bool: showFullContent, toggle } = useBoolean(!showButton.value)

const { reloadPage } = useAppStore()

async function handleNewMember() {
  await reloadPage(10)
}

async function handleCreateProject(val: SelectOption[]) {
  const { groupId } = route.params

  const cb = routerPushByKey.bind(null, "not-found")

  await fetchGroupInfo(groupId as string, cb)
  await reloadPage(10)
}

const labName = computed(() => {
  const { uid, name } = labInfo?.value ?? {}

  return name || uid || groupInfo.value?.lab_name || "Lab"
})

const groupTitle = computed(() => {
  const { name, uid } = groupInfo.value || {}

  return name || uid || "Group"
})

function setBreadcrumbs() {
  const { setDynamicBreadcrumbs } = routerStore
  const { path, name } = route

  const { uid: labUID } = labInfo.value || {}
  const { uid: groupUID } = groupInfo.value || {}

  setDynamicBreadcrumbs([
    {
      key: "labs",
      label: "All labs",
      i18nKey: "common.labs",
      breadcrumbI18nKey: "breadcrumb.myLabs",
      breadcrumbLabel: "Labs",
      routeKey: "labs",
      routePath: "/labs",
      options: [
        {
          key: "labs-my",
          label: "My labs",
          i18nKey: "page.labs.my",
          breadcrumbI18nKey: "breadcrumb.myLabs",
          breadcrumbLabel: "My labs",
          routeKey: "labs-my" satisfies App.Global.RouteKey,
          routePath: "my",
        },
        // {
        //   key: "labs-public",
        //   label: "Public labs",
        //   i18nKey: "page.labs.public",
        //   breadcrumbI18nKey: "breadcrumb.publicLabs",
        //   breadcrumbLabel: "Public labs",
        //   routeKey: "labs-public" satisfies App.Global.RouteKey,
        //   routePath: "public",
        // },
      ],
    },
    {
      breadcrumbLabel: labUID || "",
      key: "",
      label: labUID || "",
      routeKey: "lab" as App.Global.RouteKey,
      routePath: "/lab",
      to: {
        name: "lab-projects",
        params: { labUid: labUID },
      },
    },
    {
      breadcrumbLabel: "Groups",
      key: "lab-groups",
      label: "Groups",
      routeKey: "lab-groups" satisfies App.Global.RouteKey,
      routePath: "groups",
      options: [
        {
          key: "lab-projects",
          label: "Lab projects",
          i18nKey: "page.labs.projects",
          breadcrumbI18nKey: "breadcrumb.myProjects",
          breadcrumbLabel: "Lab projects",
          routeKey: "lab-projects" satisfies App.Global.RouteKey,
          routePath: "projects",
        },
        {
          key: "lab-groups",
          label: "Lab groups",
          i18nKey: "page.labs.groups",
          breadcrumbI18nKey: "breadcrumb.groups",
          breadcrumbLabel: "Lab groups",
          routeKey: "lab-groups" satisfies App.Global.RouteKey,
          routePath: "groups",
        },
        {
          key: "lab-members",
          label: "Lab members",
          i18nKey: "page.labs.members",
          breadcrumbI18nKey: "breadcrumb.allMembers",
          breadcrumbLabel: "Lab members",
          routeKey: "lab-members" satisfies App.Global.RouteKey,
          routePath: "members",
        },
      ],
    },
    {
      breadcrumbLabel: groupUID || "",
      key: "",
      label: groupUID || "",
      routeKey: name as App.Global.RouteKey,
      routePath: path,
    },
  ])
}

onMounted(async () => {
  const { path, name } = route
  const { setDynamicBreadcrumbs } = routerStore

  if (name === "labs-my" || name === "labs-public") {
    setDynamicBreadcrumbs([])
    return
  }

  const { userInfo } = authStore
  const { groupId, labUid } = route.params
  const cb = routerPushByKey.bind(null, "not-found")
  const [currGroupInfo, currLabInfo] = await Promise.all([
    fetchGroupInfo(groupId as string, cb),
    fetchLabInfoByUid(labUid as string, cb),
  ])

  labInfo.value = currLabInfo
  if (!currGroupInfo || !currGroupInfo.users) {
    return
  }
  else if (
    currGroupInfo.type === 1
    && currGroupInfo.users.findIndex(({ id }) => id === userInfo.id) === -1
  ) {
    groupInfo.value = null
    await routerPushByKey("no-permission")
    return
  }

  setBreadcrumbs()
})

onUpdated(async () => {
  await fetchLabInfoByUid(route.params.labUid as string, routerPushByKey.bind(null, "not-found"))
  await nextTick(() => {
    setBreadcrumbs()
  })
})

onUnmounted(() => {
  const { name } = route

  if (name === "labs-my" || name === "labs-public") {
    return
  }
  const { setDynamicBreadcrumbs } = routerStore
  setDynamicBreadcrumbs([])
})
</script>

<style scoped lang="sass"></style>
