<template>
  <add-record-layout
    v-if="protocolInfo"
    v-model:collapsed="isCollapsed"
    v-model:split-size="splitSize"
    v-model:selected-tab="selectedTab"
    :wrapper="wrapper"
    @update:collapsed="handleUpdateCollapsed"
  >
    <template #tabs>
      <n-tab-pane
        name="protocol-detail" class="relative" :tab="$t('common.fields')"
        display-directive="show"
        :style="{ paddingLeft: isCollapsed ? '32px' : undefined }"
      >
        <template #tab>
          <hub-protocol-menu-icon
            :selected="selectedTab === 'protocol-detail'" data-tab="protocol-detail"
            @click="handleCollapse"
          />
        </template>
        <div v-show="!isCollapsed" class="scrollable bg-white px-4 space-y-4">
          <div class="flex flex-wrap gap-4">
            <add-to-bookmarker-modal
              type="protocol"
              :starred="isStarred"
              :tooltip="$t('page.hub.protocolCard.addToBookmarks')"
              :icon-props="{ size: 18, color: isStarred ? '#E3B341' : '#A1A4AF' }"
              :protocol-id="protocolInfo?.id"
              @modal:add-to-bookmarker="handleStarredFoldersChange"
            >
              <template #trigger>
                <span>
                  {{ $t("common.star") }}
                  <n-tag size="tiny" class="ml-1">
                    {{ protocolInfo?.stars_count }}
                  </n-tag>
                </span>
              </template>
            </add-to-bookmarker-modal>
            <apply-protocol-modal
              show-trigger
              :protocol-id="protocolInfo?.id"
              :button-props="{ class: 'min-w-25' }"
              :icon-props="{ size: 16 }"
              :trigger="$t('common.reuse')"
              :label="$t('common.reuse')"
              title="Reuse protocol"
              @modal:apply-protocol="handleProtocolApplied"
            >
              <template #icon>
                <n-icon>
                  <icon-ion-document-outline />
                </n-icon>
              </template>
            </apply-protocol-modal>
            <n-button @click="handleDownload(protocolInfo?.latest_version)">
              <template #icon>
                <n-icon>
                  <icon-carbon-download />
                </n-icon>
              </template>
              {{ $t("common.download") }}
            </n-button>
            <template v-if="hasPermission">
              <!-- <n-button @click="handleEdit">
                Edit
              </n-button> -->
              <!-- <n-button @click="handleReupload"></n-button> -->
              <tooltip-button :tooltip="$t('page.protocol.tooltips.editReadOnly')" :icon="EditIcon" @click="handleEdit">
                {{ $t("common.edit") }}
              </tooltip-button>
              <tooltip-button :tooltip="$t('page.protocol.tooltips.reupload')" :icon="UploadIcon" @click="handleReupload">
                {{ $t("common.reupload") }}
              </tooltip-button>
            </template>
          </div>
          <protocol-stats-card
            :protocol-id="protocolInfo?.id"
            :download-count="0"
            :stars="protocolInfo?.stars_count"
            :records="protocolInfo?.records_count"
            :reuse-count="protocolInfo?.forks_count"
            :version="protocolInfo?.latest_version"
            :last-updated="protocolInfo?.created_at"
            :license="protocolInfo?.metadata?.license"
            :created-at="protocolInfo?.created_at"
            records-clickable
            @records-click="handleRecordsClick"
          />
          <!-- Categories and Tags Card -->
          <protocol-categories-card
            v-if="(protocolInfo?.disciplines && protocolInfo.disciplines.length > 0) || (protocolInfo?.keywords && protocolInfo.keywords.length > 0)"
            :discipline="protocolInfo?.disciplines || []"
            :keywords="protocolInfo?.keywords || []"
          />
          <protocol-info-card :protocol-info="protocolInfo" />
        </div>
      </n-tab-pane>
      <n-tab-pane
        v-if="showAssistant"
        name="ai-assistant" class="relative" :tab="$t('chat.askAira')"
        display-directive="show"
        :style="{ paddingLeft: isCollapsed ? '32px' : undefined }"
      >
        <template #tab>
          <ai-menu-icon
            outlined :selected="selectedTab === 'ai-assistant'" data-tab="ai-assistant"
            @click="handleCollapse"
          />
        </template>
        <div v-show="!isCollapsed" class="h-full pl-4">
          <div class="mb-2 h-10 w-fit rounded bg-[#2B2B38] px-4 text-[1.125rem] text-white leading-10">
            {{ $t("chat.askAira") }}
          </div>
          <chat-component
            ref="chatRef"
            v-model:full-screen="appStore.fullContent"
            v-model:role="role"
            v-model:could-change-role="couldChangeRole"
            v-model:collapsed="isCollapsed"
            v-model:docked="docked"
            hide-collapse
            :class="appStore.fullContent ? 'h-screen' : 'h-[calc(100%-3rem)]'"
            :protocol-id="protocolInfo?.id"
            source="protocol"
            enable-tool-action
            :airalogy-id="protocolInfo?.airalogy_id"
            class="w-full"
            v-bind="chatProps"
            :resolve-file="getCachedAttachment"
            @update:docked="handleUpdateDocked"
          />
        </div>
      </n-tab-pane>
    </template>
    <template #content>
      <slot />
    </template>
  </add-record-layout>
</template>

<script setup lang="ts">
import type { IProps as ChatProps } from "@airalogy/components/chat/composables/useChatInfoStore"
import type { ProtocolModels } from "@airalogy/shared/types"
import type { Component } from "vue"
import ChatComponent from "@/components/chat/index.vue"
import AddToBookmarkerModal, { type StarredFolder } from "@/components/common/add-to-bookmarker-modal.vue"
import StickyFillWrapper from "@/components/common/sticky-fill-wrapper.vue"
import AddRecordLayout from "@/components/custom/add-record-layout.vue"
import HubProtocolMenuIcon from "@/components/icon/hub-protocol-menu-icon.vue"
import ProtocolInfoCard from "@/components/protocol/protocol-info-card.vue"
import { useRouterPush } from "@/composables/useRouterPush"
import { getCachedAttachment } from "@/service/api/attachments"
import { getDownloadPackage } from "@/service/api/project-protocols"
import { getStars, StarResourceType } from "@/service/api/star"
import { useAppStore } from "@/store/modules/app"
import { useAuthStore } from "@/store/modules/auth"
import ApplyProtocolModal from "@/views/hub/components/apply-protocol-modal.vue"
import ProtocolCategoriesCard from "@/views/hub/components/protocol-categories-card.vue"
import ProtocolStatsCard from "@/views/hub/components/protocol-stats-card.vue"
import { useProtocolInfoStore } from "@/views/project-protocols/hooks/useProtocolInfoStore"
import { useClosableMessage } from "@airalogy/composables"
import { $t } from "@airalogy/shared/locales"
import EditIcon from "~icons/ion/build-outline"
import UploadIcon from "~icons/ion/cloud-upload-outline"
import { useOrProvideProjectInfoStore } from "../hooks/useProjectInfoStore"

interface IProps {
  protocol?: ProtocolModels.ProjectProtocolInfo | null
  defaultSpiltSize?: number
  chatProps?: ChatProps
  defaultSelectedTab?: "ai-assistant" | "protocol-detail"
}

const props = withDefaults(defineProps<IProps>(), {
  protocol: null,
  defaultSpiltSize: 0.35,
  chatProps: () => ({}),
  defaultSelectedTab: "protocol-detail",
})

const wrapper: Component = (props, { slots }) => h(StickyFillWrapper, { style: { height: "100%", width: "100%", minHeight: "600px" }, offset: 20, ...props }, {
  ...slots,
  prefix: ({ position }: { position: string }) => h("div", { style: { height: "20px", width: "100%", display: position === "fixed" ? "block" : "none" } }),
})

const isCollapsed = ref(false)
const splitSize = ref(props.defaultSpiltSize)

const authStore = useAuthStore()
const showAssistant = computed(() => authStore.isLogin)
const selectedTab = ref<"ai-assistant" | "protocol-detail" | undefined>(
  showAssistant.value ? props.defaultSelectedTab : "protocol-detail",
)
const appStore = useAppStore()
const { protocolInfo } = useProtocolInfoStore() || { protocolInfo: ref(props.protocol || null) }
const starredStateOverride = ref<boolean | null>(null)
const starredStateFromServer = ref<boolean | null>(null)
const starredStateRequestSeq = ref(0)
const isStarred = computed(() => {
  if (typeof starredStateOverride.value === "boolean") {
    return starredStateOverride.value
  }

  if (typeof starredStateFromServer.value === "boolean") {
    return starredStateFromServer.value
  }

  return false
})

watch(
  [() => (props.protocol || protocolInfo.value)?.id, () => authStore.isLogin],
  ([protocolId, isLoggedIn]) => {
    starredStateOverride.value = null
    starredStateFromServer.value = null

    if (!protocolId || !isLoggedIn) {
      return
    }

    void loadStarredStateFromServer(protocolId)
  },
  { immediate: true },
)

async function loadStarredStateFromServer(protocolId: string) {
  const requestSeq = ++starredStateRequestSeq.value
  const pageSize = 100
  let page = 1

  try {
    while (true) {
      const result = await getStars({
        resource_type: StarResourceType.Protocol,
        page,
        page_size: pageSize,
      })

      if (requestSeq !== starredStateRequestSeq.value) {
        return
      }

      if (!result) {
        starredStateFromServer.value = false
        return
      }

      const hasStar = result.stars.some(star => String(star.resource_id) === String(protocolId))
      if (hasStar) {
        starredStateFromServer.value = true
        return
      }

      const totalCount = result.total_count || 0
      if (page * pageSize >= totalCount) {
        starredStateFromServer.value = false
        return
      }

      page += 1
    }
  }
  catch (error) {
    if (requestSeq === starredStateRequestSeq.value) {
      starredStateFromServer.value = false
    }
  }
}

function handleStarredFoldersChange(folders: StarredFolder[]) {
  const protocolVal = props.protocol || protocolInfo.value
  if (!protocolVal) {
    return
  }

  const wasStarred = isStarred.value
  const isNowStarred = folders.length > 0
  starredStateOverride.value = isNowStarred

  if (!wasStarred && isNowStarred) {
    protocolVal.stars_count = (protocolVal.stars_count || 0) + 1
    return
  }

  if (wasStarred && !isNowStarred) {
    protocolVal.stars_count = Math.max((protocolVal.stars_count || 0) - 1, 0)
  }
}

const { routerPushByKey } = useRouterPush()
function handleProtocolApplied(data: ProtocolModels.ProtocolInfo) {
  const { lab_uid: labUid, project_uid: projectUid, uid } = data
  if (labUid && projectUid && uid) {
    routerPushByKey("protocol-info", {
      params: {
        labUid,
        projectUid,
        protocolUid: uid,
      },
    })
  }
}

function handleRecordsClick() {
  const protocolVal = props.protocol || protocolInfo.value
  if (!protocolVal?.uid || !protocolVal.lab?.uid || !protocolVal.project?.uid)
    return

  routerPushByKey("protocol-records", {
    params: {
      labUid: protocolVal.lab.uid,
      projectUid: protocolVal.project.uid,
      protocolUid: protocolVal.uid,
    },
  })
}

const role = ref<1 | 2>(1)
const couldChangeRole = ref<boolean>(false)

provide("chat-role", { role, couldChangeRole })

const chatRef = ref<{ setDocked: (val: boolean) => void } | null>(null)
const docked = ref(false)
const message = useClosableMessage()
const { hasPermission: innerHasPermission, fetchProjectInfoById } = useOrProvideProjectInfoStore(null)

const hasPermission = asyncComputed(async () => {
  const protocolVal = props.protocol || protocolInfo.value
  if (!protocolVal) {
    return false
  }

  const { user_id, project_id } = protocolVal

  if (authStore.userInfo.id === user_id) {
    return true
  }

  try {
    await fetchProjectInfoById(project_id)
    await nextTick()
    return innerHasPermission.value
  }
  catch (error) {
    return false
  }

  return false
})

function handleEdit() {
  const protocolVal = props.protocol || protocolInfo.value
  if (!protocolVal) {
    return
  }

  const { lab, project, uid, latest_version } = protocolVal
  if (!uid) {
    return
  }

  routerPushByKey("protocol-editor", {
    params: {
      labUid: lab.uid,
      projectUid: project.uid,
      protocolUid: uid,
      protocolVersion: latest_version,
    },
  })
}

function handleReupload() {
  const protocolVal = props.protocol || protocolInfo.value
  if (!protocolVal) {
    return
  }

  routerPushByKey("protocol-info-apply-protocol", {
    params: { protocolId: String(protocolVal.id) },
  })
}

function handleUpdateDocked(val: boolean) {
  if (selectedTab.value === "ai-assistant" && val) {
    chatRef.value?.setDocked(false)
  }

  if (val) {
    docked.value = true
    selectedTab.value = "protocol-detail"
  }
  else {
    docked.value = false
  }
}

function handleCollapse(e: MouseEvent) {
  const target = e.currentTarget as HTMLElement
  if (!target) {
    // NOPE
    return
  }

  const { tab } = target.dataset
  if (isCollapsed.value) {
    if (!showAssistant.value && tab === "ai-assistant") {
      selectedTab.value = "protocol-detail"
    }
    else {
      selectedTab.value = tab as "protocol-detail" | "ai-assistant"
    }

    splitSize.value = 0.35
    void nextTick(() => {
      isCollapsed.value = false
    })
  }
  else if (!tab || tab === selectedTab.value) {
    selectedTab.value = undefined

    splitSize.value = 0
    void nextTick(() => {
      isCollapsed.value = true
    })
  }
}

function handleUpdateCollapsed(val: boolean) {
  if (val || selectedTab.value) {
    return
  }

  selectedTab.value = "protocol-detail"
}

watch(
  showAssistant,
  (enabled) => {
    if (!enabled && selectedTab.value === "ai-assistant") {
      selectedTab.value = "protocol-detail"
    }
  },
  { immediate: true },
)

async function handleDownload(version?: string) {
  const { lab, project, name, id, latest_version } = protocolInfo.value || {}
  if (!id || !lab || !project || !name || !latest_version) {
    return
  }

  const tempLink = document.createElement("a")

  try {
    const { data, error } = await getDownloadPackage(id, version || latest_version)
    if (error || !data) {
      message.error("Download package failed.")
      return
    }

    tempLink.href = data.url
    tempLink.style.display = "none"
    tempLink.setAttribute("download", `${lab.name}_${project.name}_${name}_protocols_v${latest_version}.zip`)
    if (typeof tempLink.download === "undefined")
      tempLink.setAttribute("target", "_blank")

    document.body.appendChild(tempLink)
    tempLink.click()
    document.body.removeChild(tempLink)
  }
  catch (err) {
    message.error((err as Error).message)
  }
}
</script>

<style scoped lang="sass">
:deep(.protocol-content .n-tabs-nav--segment-type)
  margin: 0!important

.scrollable
  scrollbar-gutter: stable
</style>
