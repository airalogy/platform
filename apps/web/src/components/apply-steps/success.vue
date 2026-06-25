<template>
  <div class="mb-8 text-center">
    <n-result
      status="success"
      :title="title"
      :description="description"
    >
      <template #footer>
        <div class="flex flex-col items-center gap-4">
          <n-button
            type="primary"
            @click="handleNavigate('add-protocol-record')"
          >
            {{ addRecordLabel }}
          </n-button>
          <p class="text-sm text-gray-500">
            {{ redirectingText }}
          </p>
        </div>
      </template>
    </n-result>
  </div>
</template>

<script setup lang="ts">
import { useRouterPush } from "@/composables/useRouterPush"
import { $t } from "@/locales"
import { getProjectInfoById } from "@/service/api/projects"
import { useProtocolInfoStore } from "@/views/project-protocols/hooks/useProtocolInfoStore"
import { useInterval } from "@vueuse/core"
import { useApplyProtocol } from "./composables/useApplyProtocolState"

const { routerReplaceByKey } = useRouterPush()
const { applyResult, selectedOption } = useApplyProtocol()

const { protocolInfo } = useProtocolInfoStore()! || { protocolInfo: ref(null) }
const countdown = ref(5)
const { pause } = useInterval(1000, {
  controls: true,
  callback: async () => {
    countdown.value--
    if (countdown.value <= 0) {
      pause()
      await handleNavigate()
    }
  },
})

const projectInfo = ref<Api.Project.MyProjectInfo | null>(null)
async function handleNavigate(type: "add-protocol-record" | "protocol-info" = "protocol-info") {
  if (!applyResult.value) {
    return
  }

  pause()
  const { uid: protocolUid, latest_version: protocolVersion, project_id: projectId, project_uid: projectUid, lab_uid: labUid } = applyResult.value
  const { lab, project } = protocolInfo.value || {}
  const targetLabUid = lab?.uid || labUid
  const targetProjectUid = project?.uid || projectUid

  if (targetLabUid && targetProjectUid && projectId) {
    routerReplaceByKey(type, {
      params: { labUid: targetLabUid, projectUid: targetProjectUid, protocolUid, protocolVersion, projectId },
    })
  }
  else {
    if (projectInfo.value) {
      routerReplaceByKey(type, {
        params: { protocolUid, protocolVersion, labUid: projectInfo.value.lab_uid, projectUid: projectInfo.value.uid },
      })
    }
    else {
      const res = await getProjectInfoById(projectId)
      if (res) {
        projectInfo.value = res
        routerReplaceByKey(type, {
          params: { protocolUid, protocolVersion, labUid: res.lab_uid, projectUid: res.uid },
        })
      }
    }
  }
}

const title = computed(() => {
  if (selectedOption.value === "upload-zip") {
    return $t("page.protocol.apply.success.titleUploaded")
  }
  return $t("page.protocol.apply.success.titleApplied")
})

const description = computed(() => {
  if (selectedOption.value === "upload-zip") {
    return $t("page.protocol.apply.success.descUploaded")
  }
  return $t("page.protocol.apply.success.descApplied")
})

const addRecordLabel = computed(() => $t("page.protocol.apply.success.addRecord"))
const redirectingText = computed(() => $t("page.protocol.apply.success.redirecting", { seconds: countdown.value }))

onUnmounted(() => {
  pause()
})
</script>
