<template>
  <global-layout>
    <content-layout v-if="tabs.length > 0" :tabs="tabs" :title="title" :title-icon="LabIcon">
      <template v-if="userLabRole === LabRole.OWNER || userLabRole === LabRole.MANAGER" #suffix>
        <create-lab-modal
          v-if="route.name === 'labs-my' && !instanceStore.isSingleLab" show-icon trigger="New Lab"
          @modal:new-lab="handleCreateLab"
        />
        <create-project-modal
          v-if="route.name === 'lab-projects'" :lab-info="labInfo" :show-select="false"
          @modal:new-project="handleCreateProject"
        />
        <global-add-member-table-modal
          v-if="route.name === 'lab-members' && labInfo?.id && !instanceStore.isSingleLab" :id="labInfo?.id" show-icon :trigger="$t('common.addMember')"
          type="lab" @modal:new-member="handleNewMember"
        />
        <single-lab-invite-modal
          v-if="route.name === 'lab-members' && labInfo?.id && instanceStore.isSingleLab && userLabRole"
          :current-role="userLabRole"
        />
        <add-project-to-group-modal
          v-if="route.name === 'lab-groups' && labInfo" :id="labInfo?.id"
          :lab-info="labInfo" :trigger="$t('page.group.addProjectToGroup')" :button-props="{ class: 'mr-2' }"
        />
        <create-group-modal
          v-if="route.name === 'lab-groups'" :lab-info="labInfo" :show-select="false" :project-list="projectList"
          @modal:new-group="handleCreateGroup"
        />
      </template>
      <template v-if="showIcon" #title>
        <div class="mt-5 flex items-center">
          <n-avatar
            v-if="Boolean(labInfo?.logo_url)" :src="labInfo!.logo_url!" :size="40" color="transparent"
            object-fit="cover"
          />
          <lab-icon v-else />
          <template v-if="Boolean(title)">
            <h2 class="ml-5 !text-6">
              {{ title }}
            </h2>
            <lock-icon v-if="labInfo?.type === 1" class="ml-2" />
            <!-- <edit-lab-modal v-if="isManager" :item="labInfo" @modal:edit-lab="handleEditLab" /> -->
          </template>
          <n-skeleton v-else width="15em" class="ml-5" />
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
import type { TabPaneProps } from "naive-ui/es/tabs"
import { useBoolean } from "@/composables"
import { useRouterPush } from "@/composables/useRouterPush"
import { LabRole } from "@/enum"
import ContentLayout from "@/layouts/content-layout/index.vue"
import GlobalLayout from "@/layouts/global-layout/index.vue"
import { useAppStore } from "@/store/modules/app"
import { useAuthStore } from "@/store/modules/auth"
import { useInstanceStore } from "@/store/modules/instance"

import { useRouteStore } from "@/store/modules/route"
import { convertDisplayname } from "@/utils/convertDisplayname"

import CreateProjectModal from "@/views/projects/modules/create-project-modal.vue"
import { $t } from "@airalogy/shared/locales"
import { h } from "vue"
import TabHintLabel from "../../components/common/tab-hint-label.vue"
import LabIcon from "../../components/icon/lab-icon.vue"
import { useLabPermissions } from "../../composables/useLabPermissions"
import AddProjectToGroupModal from "../group/modules/add-project-to-group-modal.vue"
import { useProvideLabInfoStore } from "./hooks/useLabsInfoStore"
import CreateGroupModal from "./modules/group/create-group-modal.vue"
import CreateLabModal from "./modules/lab/create-lab-modal.vue"
import SingleLabInviteModal from "./modules/lab/single-lab-invite-modal.vue"
// import EditLabModal from "./modules/lab/edit-lab-modal.vue"

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

const route = useRoute()
const instanceStore = useInstanceStore()
const routerStore = useRouteStore()
const { userInfo } = useAuthStore()

const showIconRoute = ["lab-projects", "lab-records", "lab-members", "lab-groups", "lab-settings", "project-protocols", "project-records", "project-members"]
const showIcon = computed(() => typeof route.name === "string" && showIconRoute.includes(route.name))

const { routerPushByKey } = useRouterPush()
const { fetchLabInfoByUid, labInfo, userLabRole } = useProvideLabInfoStore(null)
const { canManageLab } = useLabPermissions(labInfo)
const projectList = ref<Api.Project.MyProjectInfo[]>([])
provide("lab-project-list", projectList)

const tabs = computed((): TabPaneProps[] => {
  const { name } = route
  if (name === "labs-my" || name === "labs-public") {
    return [
      { name: "labs-my", tab: $t("page.labs.my") },
      // { name: "labs-public", tab: $t("page.labs.public") },
    ]
  }

  if (name === "lab-projects" || name === "lab-records" || name === "lab-members" || name === "lab-groups" || name === "lab-settings") {
    const membersHint = $t("page.labs.tab.membersHint")
    const groupsHint = $t("page.labs.tab.groupsHint")
    const hintTab = (label: string, hint: string) =>
      () => h(TabHintLabel, { label, hint })
    const list = [
      { name: "lab-projects", tab: $t("page.labs.projects") },
      { name: "lab-records", tab: $t("page.recordDiary.tab") },
      {
        name: "lab-members",
        tab: hintTab($t("page.labs.members"), membersHint),
      },
    ]

    if (!instanceStore.isSingleLab) {
      list.push({
        name: "lab-groups",
        tab: hintTab($t("page.labs.groups"), groupsHint),
      })
    }

    if (canManageLab.value) {
      list.push({ name: "lab-settings", tab: $t("page.labs.settings") })
    }

    return list
  }

  if (name === "project-protocols" || name === "project-records" || name === "project-members") {
    return [
      { name: "project-protocols", tab: $t("page.project.protocols") },
      { name: "project-records", tab: $t("page.recordDiary.tab") },
      { name: "project-members", tab: $t("page.project.members") },
    ]
  }

  if (name === "protocol-info") {
    return [
      { name: "protocol-detail", tab: $t("page.protocol.tab.protocols") },
      { name: "protocol-records", tab: $t("page.protocol.tab.logs") },
      { name: "protocol-discussions", tab: $t("page.protocol.tab.discussion") },
      { name: "protocol-settings", tab: $t("page.protocol.tab.settings") },
    ]
  }

  return []
})

const title = computed(() => {
  const { name } = route

  if (name === "labs-my" || name === "labs-public") {
    return "Labs"
  }

  if (name === "lab-projects" || name === "lab-records" || name === "lab-members" || name === "lab-groups" || name === "lab-settings") {
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
  await reloadPage(500)
}
async function handleCreateLab(item: Api.Lab.LabInfo) {
  const { id, uid } = item

  await routerPushByKey("lab-projects", { params: { labUid: uid } })
}
async function handleCreateProject(val: Api.Project.MyProjectInfo) {
  const { lab_id, lab_uid: labUid, uid } = val
  const labId = String(lab_id)

  if (!labId || !uid) {
    return
  }

  await routerPushByKey("project-protocols", { params: { labUid, projectUid: uid } })
}

async function handleCreateGroup(val: Api.Groups.MyGroupsInfo) {
  const { lab_id, id, lab_uid: labUid } = val
  const labId = String(lab_id)
  const groupId = String(id)

  if (!labId || !groupId) {
    return
  }

  await routerPushByKey("lab-group-projects", { params: { labUid, groupId } })
}
async function setBreadcrumbs() {
  const { setDynamicBreadcrumbs } = routerStore
  const { path, name } = route

  const { name: displayName, uid: labUid } = labInfo.value || {}
  const convertedName = await convertDisplayname(displayName)

  setDynamicBreadcrumbs([
    {
      breadcrumbLabel: labUid || "",
      key: "",
      label: labUid || "",
      routeKey: "lab" as App.Global.RouteKey,
      routePath: "/lab",
    },
  ])
}

// async function handleEditLab() {
//   const currLabInfo = await fetchLabInfoByUid(
//     route.params.labUid as string,
//     routerPushByKey.bind(null, "lab-not-found"),
//   )

//   if (!currLabInfo || !currLabInfo.users) {
//     return
//   }
//   else if (
//     currLabInfo.type === 1
//     && currLabInfo.users.findIndex(({ id }) => id === userInfo.id) === -1
//   ) {
//     labInfo.value = null
//     await routerPushByKey("no-permission")
//     return
//   }

//   await nextTick(async () => {
//     await setBreadcrumbs()
//     await reloadPage(10)
//   })
// }

onMounted(async () => {
  const { path, name } = route
  const { setDynamicBreadcrumbs } = routerStore

  if (name === "labs-my" || name === "labs-public") {
    setDynamicBreadcrumbs([])
    return
  }

  const currLabInfo = await fetchLabInfoByUid(
    route.params.labUid as string,
    routerPushByKey.bind(null, "lab-not-found"),
  )

  if (!currLabInfo || !currLabInfo.users) {
    // TODO
  }
  else if (
    currLabInfo.type === 1
    && currLabInfo.users.findIndex(({ id }) => id === userInfo.id) === -1
  ) {
    labInfo.value = null
    await routerPushByKey("no-permission")
  }
})

onUpdated(async () => {
  const { name } = route
  const { setDynamicBreadcrumbs } = routerStore

  if (name === "labs-my" || name === "labs-public") {
    setDynamicBreadcrumbs([])
    return
  }
  if (!route.params.labUid) {
    labInfo.value = null
    return
  }

  if ((labInfo.value && labInfo.value.uid !== route.params.labUid)) {
    labInfo.value = null
  }

  if (!labInfo.value) {
    await fetchLabInfoByUid(route.params.labUid as string, routerPushByKey.bind(null, "not-found"))
  }
})

watch(labInfo, async (info) => {
  if (info) {
    await setBreadcrumbs()
  }
}, { immediate: true, deep: true })

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
