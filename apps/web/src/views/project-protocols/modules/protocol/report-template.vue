<template>
  <section v-if="Boolean(props.item?.aimd)">
    <header v-if="props.showActions" class="flex border-b py-6">
      <div class="mr-auto flex-center">
        <span v-if="parentProtocolInfo" class="block w-full">
          {{ $t("page.protocol.reusedFrom") }}
          <protocol-path-tooltip :protocol-info="parentProtocolInfo" />
        </span>
        <n-skeleton v-else-if="isFetchingInfo" width="40em" />
      </div>
      <add-log-modal
        v-if="canOpenDataEntryForOthers"
        :protocol-id="props.item.id"
        :trigger="$t('page.protocol.addRecord.title')"
        :lab-uid="props.item.lab.uid "
        :project-uid="props.item.project.uid"
        :protocol-uid="props.item.uid"
      />
      <apply-protocol-modal
        ref="applyProtocolModalRef"
        :protocol-id="props.item.id"
        :label="$t('common.reuse')"
        :title="`Reuse ${props.item.name} to another project`"
        :show-trigger="false"
      />

      <n-dropdown v-if="canManageOwnProtocols || canManageOthersProtocols" trigger="click" :options="actionList" :render-option="renderDropdownOption">
        <n-button icon-placement="right" class="ml-3">
          {{ $t("common.more") }}
          <template #icon>
            <n-icon :component="DropdownIcon" />
          </template>
        </n-button>
      </n-dropdown>
    </header>

    <main class="relative min-h-40 pt-5">
      <n-spin :show="!Boolean(props.item)">
        <!-- <edit-protocol v-if="isEdit" :protocol="protocol" :protocol-id="props.item?.id" /> -->
        <aimd-markdown-preview
          v-if="props.item?.aimd"
          :content="props.item.aimd"
          :mermaid-component="MermaidBlock"
          :resolve-url="resolveProtocolFile"
          body-class="markdown-body"
          mode="preview"
        />
        <!-- <asset-teleport
          v-if="domMounted && props.item"
          :uuid="props.item.id"
        /> -->
      </n-spin>
    </main>
  </section>
  <n-skeleton v-else class="h-full w-full flex-center flex-col" />
</template>

<script setup lang="ts">
import type { ProtocolModels } from "@airalogy/shared/types"
import type { RenderOption } from "naive-ui/es/dropdown/src/interface"
import ProtocolPathTooltip from "@/components/protocol/protocol-path-tooltip.vue"

import { useBoolean, useLoading, useProjectPermissions } from "@/composables"
import { useRouterPush } from "@/composables/useRouterPush"
import {
  getDownloadPackage,
  getProtocolInfo,
} from "@/service/api/project-protocols"
import { request } from "@/service/request"
import { resolveProtocolFile as resolveProtocolFileUtil } from "@/utils/resolveProtocolFile"
import ApplyProtocolModal from "@/views/hub/components/apply-protocol-modal.vue"
import AddLogModal from "@/views/project-protocols/modules/add-log-modal.vue"
import { AimdMarkdownPreview } from "@airalogy/aimd-renderer/vue"
import MermaidBlock from "@airalogy/components/markdown-editor/modules/mermaid/mermaid-block.vue"
import { useClosableMessage } from "@airalogy/composables"
import { $t } from "@airalogy/shared/locales"
import EditIcon from "~icons/ion/build-outline"
import DownloadIcon from "~icons/ion/cloud-download-outline"
import UploadIcon from "~icons/ion/cloud-upload-outline"
import DropdownIcon from "~icons/local/dropdown-outline"
import ReuseIcon from "~icons/local/reuse"

import { type DropdownOption, NIcon, NTooltip } from "naive-ui"
import { nanoid } from "nanoid"
import { useOrProvideProjectInfoStore } from "../../hooks/useProjectInfoStore"

interface IProps {
  item: ProtocolModels.ProjectProtocolInfo
  showActions?: boolean
}

const props = withDefaults(defineProps<IProps>(), {
  showActions: true,
})

const { projectInfo } = useOrProvideProjectInfoStore(null)
const { canOpenDataEntryForOthers, canManageOwnProtocols, canManageOthersProtocols } = useProjectPermissions(projectInfo)
const { bool: isFetchingInfo, setFalse: endFetchingInfo, setTrue: startFetchingInfo } = useBoolean()

const message = useClosableMessage()
const applyProtocolModalRef = ref<{ showModal: () => void }>()

// Resolve file paths for protocol assets
async function resolveProtocolFile(src: string): Promise<{ url: string } | null> {
  if (!props.item?.id)
    return null
  return resolveProtocolFileUtil(src, props.item.id)
}

async function handleDownload(version?: string) {
  const { lab, project, name, id, latest_version } = props.item
  const tempLink = document.createElement("a")

  try {
    const { data, error } = await getDownloadPackage(id, version || latest_version)
    if (error || !data) {
      message.error("Download package failed.")
      return
    }
    tempLink.href = data.url
    tempLink.style.display = "none"
    tempLink.setAttribute("download", `${lab.name}_${project.name}_${name}_protocols.zip`)
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

const { routerPushByKey } = useRouterPush()

function handleApplyProtocol() {
  void routerPushByKey("protocol-info-apply-protocol", {
    params: { protocolId: String(props.item.id) },
  })
}

function handleReuseProtocol() {
  applyProtocolModalRef.value?.showModal()
}

const renderDropdownOption: RenderOption = ({ option, node }) => {
  return h(
    NTooltip,
    { keepAliveOnHover: false, style: { width: "max-content" } },
    {
      default: () => option.tooltip,
      trigger: () => [node],
    },
  )
}

const { loadingState, startTargetLoading, endTargetLoading } = useLoading(false, ["edit"])
const actionList = computed<DropdownOption[] >(() => [
  {
    label: $t("common.edit"),
    key: "edit",
    tooltip: "View this protocol in the editor. This version is read-only; click the lock icon to create an editable copy.",
    icon: () => h(NIcon, null, { default: () => h(EditIcon) }),
    loading: loadingState.value.edit,
    props: {
      onClick: async () => {
        startTargetLoading("edit")
        const { lab, project, uid, latest_version } = props.item
        if (!uid) {
          return
        }

        await routerPushByKey("protocol-editor", {
          params: {
            labUid: lab.uid,
            projectUid: project.uid,
            protocolUid: uid,
            protocolVersion: latest_version,
          },
        })
        endTargetLoading("edit")
      },
    },
  },
  {
    label: $t("common.download"),
    key: "download",
    tooltip: "Download the Protocol in ZIP format",
    icon: () => h(NIcon, null, { default: () => h(DownloadIcon) }),
    props: {
      onClick: () => handleDownload(props.item.latest_version),
    },
  },
  {
    label: $t("common.reupload"),
    key: "reupload",
    tooltip: "Update the current Protocol by uploading a new ZIP file (this will overwrite the existing Protocol)",
    icon: () => h(NIcon, null, { default: () => h(UploadIcon) }),
    props: {
      onClick: handleApplyProtocol,
    },
  },
  {
    label: $t("common.reuse"),
    key: "reuse",
    tooltip: "Reuse the Protocol to another project",
    icon: () => h(NIcon, { size: 12 }, { default: () => h(ReuseIcon) }),
    props: {
      onClick: handleReuseProtocol,
    },
  },
])

const parentProtocolInfo = ref<ProtocolModels.ProjectProtocolInfo | null>(null)

const requestId = ref<string | null>(null)
watchEffect(async () => {
  parentProtocolInfo.value = null

  const { parent_protocol_id } = props.item

  if (parent_protocol_id) {
    requestId.value = nanoid()
    startFetchingInfo()
    try {
      const res = await getProtocolInfo(parent_protocol_id, undefined, false, requestId.value)
      if (res && res.data) {
        parentProtocolInfo.value = res.data as ProtocolModels.ProjectProtocolInfo
      }
    }
    catch (e) {
      //
    }
    finally {
      endFetchingInfo()
    }
  }

  return () => {
    if (requestId.value) {
      request.cancelRequest(requestId.value)
      requestId.value = null
    }
  }
})
</script>
