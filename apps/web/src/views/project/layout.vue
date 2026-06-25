<template>
  <global-layout>
    <content-layout :title="projectTitle" :tabs="tabs">
      <template v-if="canCreateProtocol || canShowSettings" #suffix>
        <div class="w-40 text-right">
          <add-protocol-modal
            v-if="route.name === 'project-protocols' && canCreateProtocol"
            :compact="false"
            show-icon
            :trigger="$t('common.newProtocol')"
            :project="projectInfo"
            :show-select="false"
            @modal:new-protocol="handleAddProtocol"
          />
          <global-add-member-table-modal
            v-if="route.name === 'project-members' && projectInfo?.id && canShowSettings "
            :id="projectInfo?.id"
            show-icon
            :trigger="$t('common.addMember')"
            type="project"
            :is-private="projectInfo.type === ProjectType.PRIVATE"
            @modal:new-member="handleAddMember"
          />
        </div>
      </template>
      <template v-if="showIcon" #title>
        <div class="mt-5 flex items-center">
          <project-icon />
          <template v-if="projectInfo">
            <router-link
              v-if="authStore.isLogin"
              :to="{ name: 'lab-projects', params: { labUid: projectInfo?.lab_uid } }"
              class="ml-5 text-6 color-text-secondary"
            >
              {{ projectInfo?.lab_name || projectInfo?.lab_uid }}
            </router-link>
            <span v-else class="ml-5 text-6 color-text-secondary">
              {{ projectInfo?.lab_name || projectInfo?.lab_uid }}
            </span>
            <span class="mx-3 select-none text-5 color-text-secondary">/</span>
            <h2 class="!text-6">
              {{ projectTitle }}
            </h2>
            <span
              v-if="visibilityLabel"
              class="ml-2 inline-flex items-center whitespace-nowrap rounded px-2 py-0.5 text-xs font-500"
              :class="visibilityClass"
            >
              {{ visibilityLabel }}
            </span>
            <!-- <edit-project-modal
              v-if="projectInfo?.create_user_id === userInfo.id"
              :item="projectInfo"
              @modal:edit-project="handleEditProject"
            /> -->
          </template>
          <n-skeleton v-else width="20rem" class="mx-4" />
        </div>
        <n-card v-if="Boolean(description)" bordered class="mt-5 w-full md:w-70%" content-class="!text-4">
          <div :class="{ 'line-clamp-3': !showFullContent }">
            {{ description }}
          </div>
          <n-button v-if="showButton" inline @click="toggle">
            {{ showFullContent ? "Show Less" : "Read More" }}
          </n-button>
        </n-card>
      </template>
    </content-layout>
  </global-layout>
</template>

<script setup lang="ts">
import type { TabPaneProps } from "naive-ui/es/tabs"
import { useBoolean, useProjectPermissions } from "@/composables"
import { useProjectVisibility } from "@/composables/useProjectVisibility"
import { useRouterPush } from "@/composables/useRouterPush"
import { useSeoMeta } from "@/composables/useSeoMeta"
import ContentLayout from "@/layouts/content-layout/index.vue"
import GlobalLayout from "@/layouts/global-layout/index.vue"

import { useAppStore } from "@/store/modules/app"
import { useAuthStore } from "@/store/modules/auth"
import { useRouteStore } from "@/store/modules/route"
import { buildPublicProjectPath, buildSeoUrl } from "@/utils/seo"
import { $t } from "@airalogy/shared/locales"

import { computed, h, onMounted } from "vue"
import TabHintLabel from "../../components/common/tab-hint-label.vue"
import { LAB_OWNER_AND_MANAGER } from "../../composables/useLabPermissions"
import { ProjectType } from "../../enum"
import { useProvideProjectInfoStore } from "../project-protocols/hooks/useProjectInfoStore"
import AddProtocolModal from "../project-protocols/modules/add-protocol-modal.vue"

defineOptions({
  name: "ProjectLayout",
})

withDefaults(defineProps<Props>(), {
  showPadding: false,
})

interface Props {
  /** Show padding for content */
  showPadding?: boolean
}

const route = useRoute()
const authStore = useAuthStore()
const showIcon = computed(
  () =>
    route.name === "lab-projects"
    || route.name === "lab-members"
    || route.name === "project-protocols"
    || route.name === "project-records"
    || route.name === "project-members"
    || route.name === "project-settings",
)

const { routerPushByKey } = useRouterPush()
const { refetchProjectInfo, projectInfo } = useProvideProjectInfoStore(null)

const { canShowSettings: canShowProjectSettings, canCreateProtocol } = useProjectPermissions(projectInfo)
const canShowSettings = computed(() =>
  canShowProjectSettings.value || LAB_OWNER_AND_MANAGER.includes(projectInfo.value?.user_lab_role),
)

const membersHint = computed(() => $t("page.project.tab.membersHint"))

const baseTabs = computed<(TabPaneProps & { name: App.Global.TabKey })[]>(() => {
  const hintTab = (label: string, hint: string) =>
    () => h(TabHintLabel, { label, hint })
  const tabs: (TabPaneProps & { name: App.Global.TabKey })[] = [
    { name: "project-protocols", tab: $t("page.project.tab.protocols") },
  ]

  if (authStore.isLogin) {
    tabs.push({ name: "project-records", tab: $t("page.recordDiary.tab") })
    tabs.push({ name: "project-members", tab: hintTab($t("page.project.tab.members"), membersHint.value) })
  }

  return tabs
})

const tabs = computed(() => canShowSettings.value ? [...baseTabs.value, { name: "project-settings", tab: $t("page.project.tab.settings") }] : baseTabs.value)

const projectTitle = computed(() => {
  const { name, uid } = projectInfo.value || {}

  return name || uid || "Project"
})

const { visibilityLabel, visibilityClass } = useProjectVisibility(() => projectInfo.value?.type)

const description = computed(() => {
  return projectInfo.value?.description ?? ""
})

const publicProjectSeo = computed(() => {
  const info = projectInfo.value
  if (!info || route.name !== "project-protocols") {
    return null
  }

  const projectName = info.name || info.uid || "Project"
  const canonicalPath = buildPublicProjectPath({
    labUid: info.lab_uid,
    projectUid: info.uid,
  })
  const seoDescription = info.description?.trim()
    || `${projectName} is a public project on Airalogy for sharing protocols and reproducible research workflows.`
  const image = info.logo_url || "/images/project_placeholder.png"

  return {
    title: `${projectName} | Public Project | Airalogy`,
    description: seoDescription,
    canonical: canonicalPath,
    robots: "index,follow",
    ogType: "website" as const,
    image,
    modifiedTime: info.updated_at || null,
    jsonLd: {
      "@context": "https://schema.org",
      "@type": "CollectionPage",
      "name": projectName,
      "description": seoDescription,
      "url": buildSeoUrl(canonicalPath),
      "image": buildSeoUrl(image),
      "dateModified": info.updated_at || undefined,
      "isPartOf": {
        "@type": "WebSite",
        "name": "Airalogy",
        "url": buildSeoUrl("/"),
      },
    },
  }
})

useSeoMeta(publicProjectSeo)

const showButton = computed(() => description.value.length > 1000)

const { bool: showFullContent, toggle } = useBoolean(!showButton.value)

const { reloadPage } = useAppStore()

function handleAddProtocol(payload: {
  id: string
  uid: string
  labUid: string
  labId: string
  projectUid: string
  name: string
}) {
  const { uid, projectUid, labUid } = payload
  void routerPushByKey("protocol-info", {
    params: {
      labUid,
      protocolUid: uid,
      projectUid,
    },
  })
}
async function handleAddMember() {
  await reloadPage(500)
}

const routerStore = useRouteStore()

async function setBreadcrumbs(info?: Api.Project.MyProjectInfo | null) {
  if (!info) {
    return
  }

  const { setDynamicBreadcrumbs } = routerStore

  const { lab_uid: labUid, uid: projectUid, parent_project_uid: parentProjectUid, parent_project_name: parentProjectName } = info || {}

  const breadcrumbs: any[] = [
    {
      breadcrumbLabel: labUid || "",
      key: "",
      label: labUid || "",
      routeKey: "lab" as App.Global.RouteKey,
      routePath: "/lab",
      to: authStore.isLogin
        ? {
            name: "lab-projects",
            params: { labUid },
          }
        : undefined,
    },
  ]

  if (parentProjectUid) {
    breadcrumbs.push({
      breadcrumbLabel: parentProjectUid,
      key: "",
      label: parentProjectName || parentProjectUid,
      routeKey: "project-protocols" as App.Global.RouteKey,
      routePath: "/project",
      to: {
        name: "project-protocols",
        params: { labUid, projectUid: parentProjectUid },
      },
    })
  }

  breadcrumbs.push(
    {
      breadcrumbLabel: projectUid || "",
      key: "",
      label: projectUid || "",
      routeKey: "project-protocols" as App.Global.RouteKey,
      routePath: "/project",
      options: [
        {
          key: "project-protocols",
          label: "Project protocols",
          i18nKey: "page.project.protocols",
        },
        {
          key: "project-records",
          label: "Project records",
          i18nKey: "page.recordDiary.tab",
          breadcrumbLabel: "Project records",
        },
        {
          key: "project-members",
          label: "Project members",
          i18nKey: "page.project.members",
          breadcrumbLabel: "Project members",
        },
      ],
    },
  )

  setDynamicBreadcrumbs(breadcrumbs)
}

async function handleEditProject() {
  const { labUid, projectUid } = route.params

  const currProjectInfo = await refetchProjectInfo(0, {
    labUid: labUid as string,
    projectUid: projectUid as string,
  })

  if (currProjectInfo) {
    projectInfo.value = currProjectInfo
  }
  else {
    routerPushByKey("project-not-found")
  }

  await nextTick(async () => {
    await setBreadcrumbs()
    await reloadPage(10)
  })
}

async function loadProjectInfo() {
  const { name } = route
  const { setDynamicBreadcrumbs } = routerStore

  if (name === "project-dashboard" || name === "labs-public") {
    setDynamicBreadcrumbs([])
    return
  }

  const { labUid, projectUid } = route.params
  const currProjectInfo = await refetchProjectInfo(0, {
    labUid: labUid as string,
    projectUid: projectUid as string,
  })

  if (currProjectInfo) {
    await setBreadcrumbs(currProjectInfo)
  }
  else {
    routerPushByKey("project-not-found")
  }
}

watch(
  [() => route.params.labUid, () => route.params.projectUid],
  async ([labUid, projectUid], [prevLabUid, prevProjectUid]) => {
    if (!labUid || !projectUid) {
      return
    }

    if (labUid === prevLabUid && projectUid === prevProjectUid) {
      return
    }

    await loadProjectInfo()
  },
  { immediate: true },
)

onUnmounted(() => {
  const { setDynamicBreadcrumbs } = routerStore
  setDynamicBreadcrumbs([])
})
</script>

<style scoped lang="sass">
:deep(.project-members-tab .n-tabs-tab__label)
  display: inline-flex
  align-items: center
  gap: 6px

:deep(.project-members-tab .n-tabs-tab__label::after)
  content: "?"
  display: inline-flex
  align-items: center
  justify-content: center
  width: 14px
  height: 14px
  border: 1px solid #A1A4AF
  border-radius: 9999px
  font-size: 10px
  line-height: 1
  color: #A1A4AF
  transform: translateY(-1px)
</style>
