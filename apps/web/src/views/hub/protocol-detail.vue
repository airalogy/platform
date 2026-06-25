<template>
  <global-layout>
    <content-layout
      :tabs="tabs"
      title="Protocol Detail"
      initial-active-tab="hub-detail-protocol"
      :show-content-spin="true"
    >
      <template #title>
        <protocol-header :protocol="protocolInfo" :is-starred="isStarred" />
      </template>
    </content-layout>
  </global-layout>
</template>

<script setup lang="ts">
import type { TabPaneProps } from "naive-ui/lib"
import { useSeoMeta } from "@/composables/useSeoMeta"
import ContentLayout from "@/layouts/content-layout/index.vue"
import GlobalLayout from "@/layouts/global-layout/index.vue"
import { useAppStore } from "@/store/modules/app"
import { useRouteStore } from "@/store/modules/route"
import { buildPublicProtocolPath } from "@/utils/seo"
import { useProvideProtocolInfoStore } from "@/views/project-protocols/hooks/useProtocolInfoStore"
import { $t } from "@airalogy/shared/locales"
import { useRoute } from "vue-router"
import ProtocolHeader from "./components/protocol-header.vue"

const route = useRoute()

// Active tab management
const activeTab = ref("hub-detail-protocol")
const tabs = computed((): TabPaneProps[] => {
  return [
    { name: "hub-detail-protocol", tab: $t("page.protocol.tab.protocols") },
    { name: "hub-detail-record", tab: $t("page.protocol.tab.logs") },
    { name: "hub-detail-discussion", tab: $t("page.protocol.tab.discussion") },
    // { name: "unit-settings", tab: $t("page.protocol.tab.settings") },
  ]
})

const appStore = useAppStore()

const { protocolInfo, fetchProtocolInfoByUid } = useProvideProtocolInfoStore(null)
// Add loading state

const isStarred = ref(false)

const hubProtocolSeo = computed(() => {
  if (!protocolInfo.value) {
    return null
  }

  const { uid, name, description, lab, project } = protocolInfo.value
  const protocolName = name || uid || "Protocol"
  const canonicalPath = buildPublicProtocolPath({
    labUid: lab?.uid,
    projectUid: project?.uid,
    protocolUid: uid,
  })
  const seoDescription = description?.trim()
    || `${protocolName} is a public protocol shared on Airalogy Hub.`
  const pageTitle = route.name === "hub-detail-record"
    ? `${protocolName} Hub Records | Airalogy`
    : route.name === "hub-detail-discussion"
      ? `${protocolName} Hub Discussions | Airalogy`
      : `${protocolName} | Airalogy Hub`

  return {
    title: pageTitle,
    description: seoDescription,
    canonical: canonicalPath,
    robots: "noindex,follow",
    ogType: "website" as const,
    image: "/images/research_placeholder.png",
  }
})

useSeoMeta(hubProtocolSeo)

function handleTabChange(tab: string) {
  activeTab.value = tab
}

const routerStore = useRouteStore()

function setBreadcrumbs() {
  if (!protocolInfo.value || !protocolInfo.value) {
    return
  }

  const { setDynamicBreadcrumbs } = routerStore
  const { uid } = protocolInfo.value

  setDynamicBreadcrumbs([
    {
      key: "hub",
      label: "Hub",
      breadcrumbLabel: "Hub",
      routeKey: "hub",
      routePath: "/hub",
    },
    {
      key: "hub-list",
      label: "All protocols",
      breadcrumbLabel: "All protocols",
      routeKey: "hub-list" satisfies App.Global.RouteKey,
      routePath: "list",
    },
    {
      key: "hub-detail",
      label: uid,
      breadcrumbLabel: uid,
      routeKey: "hub-detail",
      routePath: "detail",
    },
  ])
}

async function loadProtocolInfo() {
  const { labUid, projectUid, protocolUid } = route.params
  if (!labUid || !projectUid || !protocolUid) {
    return
  }

  appStore.setLoading(true)
  try {
    await fetchProtocolInfoByUid({
      labUid: labUid as string,
      projectUid: projectUid as string,
      protocolUid: protocolUid as string,
    })
    setBreadcrumbs()
  }
  finally {
    appStore.setLoading(false)
  }
}

watch(
  [() => route.params.labUid, () => route.params.projectUid, () => route.params.protocolUid],
  async ([labUid, projectUid, protocolUid], [prevLabUid, prevProjectUid, prevProtocolUid]) => {
    if (!labUid || !projectUid || !protocolUid) {
      return
    }

    if (labUid === prevLabUid && projectUid === prevProjectUid && protocolUid === prevProtocolUid) {
      return
    }

    await loadProtocolInfo()
  },
  { immediate: true },
)

watch(
  () => route.name,
  (name) => {
    if (typeof name === "string") {
      activeTab.value = name
    }
  },
  { immediate: true },
)
</script>

<style scoped lang="sass">
:deep(.n-tabs-nav-scroll-wrapper)
  &:before, &:after
    content: none
:deep(.n-tabs-tab.n-tabs-tab--active)
  background: transparent!important
  color: #333333

:deep(.n-tabs.n-tabs--left .n-tabs-nav-scroll-content)
  width: fit-content
</style>
