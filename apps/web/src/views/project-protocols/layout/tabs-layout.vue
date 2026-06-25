<template>
  <global-layout :float-button-props="floatButtonProps">
    <content-layout
      :tabs="tabs" :title="title" :initial-active-tab="initialActiveTab"
      :loading="loading" :map-tab-name="mapTabName"
    >
      <template #title>
        <protocol-title-section :protocol-info="protocolInfo" :title="title" class="mt-5" />
        <global-description v-if="protocolInfo?.description" :description="protocolInfo?.description" />
      </template>

      <template #suffix>
        <n-button
          v-if="route.name === 'protocol-discussion-detail'"
          quaternary
          type="primary"
          class="mr-3"
          @click="() => routerPushByKey('protocol-discussions', route.params)"
        >
          <n-icon class="mr-3">
            <icon-ion-arrow-back />
          </n-icon>
          Back To Discussions
        </n-button>
        <!-- <n-popover
          v-if="protocolInfo"
          trigger="hover"
          placement="bottom-end"
          :show-arrow="false"
          :theme-overrides="{ padding: '0' }"
        >
          <template #trigger>
            <n-button text type="primary">
              See All Protocol Info
              <template #icon>
                <n-icon>
                  <icon-ion-chevron-down />
                </n-icon>
              </template>
            </n-button>
          </template>
          <protocol-info-card :protocol-info="protocolInfo" />
        </n-popover> -->
      </template>
    </content-layout>

    <template v-if="protocolInfo && canOpenDataEntryForOthers" #floatButton>
      <n-tooltip trigger="hover">
        Click to add a new record
        <template #trigger>
          <n-icon :component="AddIcon" size="32" />
        </template>
      </n-tooltip>
    </template>
  </global-layout>
</template>

<script setup lang="ts">
import type { FloatButtonProps } from "naive-ui"
import type { TabPaneProps } from "naive-ui/es/tabs"
import { useLoading, useProjectPermissions } from "@/composables"
import { useRouterPush } from "@/composables/useRouterPush"
import { useSeoMeta } from "@/composables/useSeoMeta"
import ContentLayout from "@/layouts/content-layout/index.vue"
import GlobalLayout from "@/layouts/global-layout/index.vue"
import { useAuthStore } from "@/store/modules/auth"
import { useRouteStore } from "@/store/modules/route"
import { buildPublicProtocolPath, buildSeoUrl } from "@/utils/seo"
import { protocolKey } from "@/utils/template/eventKey"
import { useClosableMessage } from "@airalogy/composables"

import { $t } from "@airalogy/shared/locales"
import AddIcon from "~icons/ion/add-outline"
import IconIonArrowBack from "~icons/ion/arrow-back"
import { NButton, NIcon } from "naive-ui"
// import { getProjectInfoById } from "../../../service/api/projects"
import { useOrProvideProjectInfoStore } from "../hooks/useProjectInfoStore"
import { useProvideProtocolInfoStore } from "../hooks/useProtocolInfoStore"

defineOptions({
  name: "ProtocolTabsLayout",
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
const { protocolInfo, fetchProtocolInfoByUid } = useProvideProtocolInfoStore(null)

const initialActiveTab = computed<App.Global.TabKey>(
  () => (route.name as App.Global.TabKey) || "protocol-detail",
)

const title = computed(() => {
  if (!protocolInfo.value) {
    return ""
  }

  const { name } = protocolInfo.value

  return name
})

const protocolSeoMeta = computed(() => {
  if (!protocolInfo.value) {
    return null
  }

  const { uid, name, description, keywords, created_at, updated_at, lab, project, user, metadata } = protocolInfo.value
  const protocolName = name || uid || "Protocol"
  const canonicalPath = buildPublicProtocolPath({
    labUid: lab?.uid,
    projectUid: project?.uid,
    protocolUid: uid,
  })
  const isCanonicalProtocolPage = route.name === "protocol-detail"
  const seoDescription = description?.trim()
    || `${protocolName} is a public protocol on Airalogy for reproducible research and global knowledge sharing.`
  const pageTitle = isCanonicalProtocolPage
    ? `${protocolName} | Public Protocol | Airalogy`
    : route.name === "protocol-records"
      ? `${protocolName} Records | Airalogy`
      : route.name === "protocol-discussions"
        ? `${protocolName} Discussions | Airalogy`
        : route.name === "protocol-discussion-detail"
          ? `${protocolName} Discussion | Airalogy`
          : `${protocolName} | Airalogy`

  return {
    title: pageTitle,
    description: seoDescription,
    canonical: canonicalPath,
    robots: isCanonicalProtocolPage ? "index,follow" : "noindex,follow",
    ogType: isCanonicalProtocolPage ? "article" as const : "website" as const,
    image: "/images/research_placeholder.png",
    keywords: keywords || [],
    publishedTime: created_at || null,
    modifiedTime: updated_at || null,
    jsonLd: isCanonicalProtocolPage
      ? {
          "@context": "https://schema.org",
          "@type": "CreativeWork",
          "name": protocolName,
          "description": seoDescription,
          "url": buildSeoUrl(canonicalPath),
          "image": buildSeoUrl("/images/research_placeholder.png"),
          "datePublished": created_at || undefined,
          "dateModified": updated_at || undefined,
          "author": user?.name
            ? {
                "@type": "Person",
                "name": user.name,
              }
            : undefined,
          "keywords": keywords?.length ? keywords.join(", ") : undefined,
          "license": metadata?.license || undefined,
          "isPartOf": {
            "@type": "WebSite",
            "name": "Airalogy",
            "url": buildSeoUrl("/"),
          },
        }
      : null,
  }
})

useSeoMeta(protocolSeoMeta)

const basicTabs: TabPaneProps[] = [
  { name: "protocol-detail", tab: $t("page.protocol.tab.protocols") },
  { name: "protocol-records", tab: $t("page.protocol.tab.logs") },
  { name: "protocol-discussions", tab: $t("page.protocol.tab.discussion") },
]

const { hasPermission, projectInfo, fetchProjectInfoById } = useOrProvideProjectInfoStore(null)
const { canOpenDataEntryForOthers } = useProjectPermissions(projectInfo)

const tabs = asyncComputed(async (): Promise<TabPaneProps[]> => {
  if (!protocolInfo.value) {
    return basicTabs
  }

  if (!projectInfo.value) {
    await fetchProjectInfoById(protocolInfo.value.project_id)
    await nextTick()
  }
  if (hasPermission.value) {
    return basicTabs.concat({ name: "protocol-settings", tab: $t("page.protocol.tab.settings") })
  }

  return basicTabs
})

function mapTabName(tabName: any) {
  if (tabName === "protocol-detail" && !protocolInfo.value?.id) {
    return "protocol-info-apply-protocol"
  }
  return tabName
}
// const description = computed(() => { })
const { routerPushByKey, routerReplaceByKey, toNotFound } = useRouterPush()
const routerStore = useRouteStore()

// const labDisplayName = computed(() => {
//   const { uid, name } = labInfo?.value ?? {}

//   return name || uid || protocolInfo.value?.lab_name || "Lab"
// })

function setBreadcrumbs() {
  if (!protocolInfo.value) {
    return
  }

  const { path, name } = route
  const { setDynamicBreadcrumbs } = routerStore

  const {
    uid,
    project,
    lab,
  } = protocolInfo.value || {}

  setDynamicBreadcrumbs([
    {
      breadcrumbLabel: lab.uid || "",
      key: "",
      label: lab.uid || "",
      routeKey: "lab" as App.Global.RouteKey,
      routePath: "/lab",
      to: authStore.isLogin
        ? {
            name: "lab-projects",
            params: { labUid: lab.uid },
          }
        : undefined,
    },
    {
      breadcrumbLabel: project.uid || "",
      key: "",
      label: project.uid || "",
      routeKey: "project-protocols" as App.Global.RouteKey,
      routePath: "/project",
      to: {
        name: "project-protocols",
        params: { labUid: lab.uid, projectUid: project.uid },
      },
    },
    {
      breadcrumbLabel: protocolInfo.value.uid || "protocol",
      key: "",
      label: protocolInfo.value.uid || "protocol",
      routeKey: name as App.Global.RouteKey,
      routePath: path,
    },
  ])
}

const { loading, startLoading, endLoading } = useLoading()

const eventBus = useEventBus<"upload-protocol">(protocolKey)
eventBus.on(async (event, payload: Record<string, any>) => {
  if (event === "upload-protocol") {
    const { labUid, projectUid, protocolUid } = route.params as {
      labUid: string
      projectUid: string
      protocolUid: string
    }
    await fetchProtocolInfoByUid({ labUid, projectUid, protocolUid })
  }
})

const message = useClosableMessage()

function handleAddRecord() {
  if (!protocolInfo.value || !protocolInfo.value.id) {
    message.error("Please select a protocol first")
    const { labUid, projectUid, protocolUid } = route.params as { labUid: string, projectUid: string, protocolUid: string }

    void routerPushByKey("protocol-info-apply-protocol", {
      params: { labUid, projectUid, protocolUid },
    })
    return
  }

  const { lab, project, uid } = protocolInfo.value

  void routerPushByKey("add-protocol-record", {
    params: { labUid: lab.uid, projectUid: project.uid, protocolUid: uid },
  })
}

const floatButtonProps: FloatButtonProps & { onClick: () => void } = {
  type: "primary",
  width: 56,
  height: 56,
  right: 50,
  bottom: 50,
  onClick: handleAddRecord,
}

watch(
  () => route.params,
  async (curr, prev) => {
    const { labUid, projectUid, protocolUid } = curr
    if (!(labUid && projectUid && protocolUid)) {
      return
    }

    if (
      prev?.labUid === labUid
      && prev?.projectUid === projectUid
      && prev?.protocolUid === protocolUid
    ) {
      return
    }

    protocolInfo.value = null
    startLoading()
    const res = await fetchProtocolInfoByUid({
      labUid: labUid as string,
      projectUid: projectUid as string,
      protocolUid: protocolUid as string,
    }, false)

    if (!res) {
      // message.error("Failed to fetch protocol info")
      await toNotFound("protocol")
      return
    }

    endLoading()
  },
  { deep: true, immediate: true },
)

onMounted(async () => {
  const { path, name } = route
  const { setDynamicBreadcrumbs } = routerStore

  if (name === "labs-my" || name === "labs-public") {
    setDynamicBreadcrumbs([])
    return
  }

  await nextTick(() => {
    setBreadcrumbs()
  })
})

watch(protocolInfo, () => {
  setBreadcrumbs()
})
</script>

<style scoped lang="sass">
@use "@styles/sass/tab.sass" as *

// :deep(.n-tabs.n-tabs--left .n-tabs-nav-scroll-content)
//   padding-right: 2rem
//   margin-right: 2rem

:deep(.n-tabs.n-tabs--left .n-tabs-tab.n-tabs-tab--active)
  color: #333333
:deep(.n-tabs-pane-wrapper)
  overflow: visible!important
</style>
