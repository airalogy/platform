<template>
  <div
    class="grid grid-cols-1 mx-auto gap-6 px-4"
    :class="applyOptions.length > 3 ? 'md:grid-cols-4' : 'md:grid-cols-3'"
  >
    <n-card
      v-for="option in applyOptions"
      :key="option.type"
      hoverable
      class="transform cursor-pointer transition-all duration-200 hover:shadow-lg hover:-translate-y-1"
      content-class="flex flex-col items-center"
      @click="handleSelectOption(option.type)"
    >
      <div class="rounded-full bg-primary-50 p-4">
        <n-icon size="48" class="text-primary">
          <component :is="option.icon" />
        </n-icon>
      </div>
      <div class="mb-2 min-h-15 text-center text-xl font-semibold">
        {{ option.title }}
      </div>
      <div class="my-auto text-center text-gray-500">
        {{ option.description }}
      </div>
    </n-card>
  </div>
</template>

<script setup lang="ts">
import type { ProtocolModels } from "@airalogy/shared/types/models"
import type { ApplyOption } from "./composables/useApplyProtocolState"
import { $t } from "@/locales"
import HubIcon from "~icons/local/hub"
import IconFile from "~icons/tabler/file"
import IconFileZip from "~icons/tabler/file-zip"
import IconReportSearch from "~icons/tabler/report-search"
import { nanoid } from "nanoid"
import { useRouterPush } from "../../composables/useRouterPush"
import { useApplyProtocol } from "./composables/useApplyProtocolState"

interface IProps {
  protocolInfo?: ProtocolModels.ProjectProtocolInfo | null
}

const props = withDefaults(defineProps<IProps>(), {
  protocolInfo: undefined,
})

const { selectedOption, currentStep } = useApplyProtocol()

interface ApplyOptionConfig {
  type: ApplyOption & {}
  icon: Component
  title: string
  description: string
}

const defaultApplyOptions = computed<ApplyOptionConfig[]>(() => ([
  {
    type: "scratch",
    icon: IconFile,
    title: $t("page.protocol.apply.options.scratch.title"),
    description: $t("page.protocol.apply.options.scratch.description"),
  },
  {
    type: "upload-zip",
    icon: IconFileZip,
    title: $t("page.protocol.apply.options.uploadZip.title"),
    description: $t("page.protocol.apply.options.uploadZip.description"),
  },
  {
    type: "existing",
    icon: IconReportSearch,
    title: $t("page.protocol.apply.options.existing.title"),
    description: $t("page.protocol.apply.options.existing.description"),
  },
]))

const applyOptions = computed<ApplyOptionConfig[]>(() => {
  if (props.protocolInfo) {
    return defaultApplyOptions.value
  }
  return [
    ...defaultApplyOptions.value,
    {
      type: "hub",
      icon: HubIcon,
      title: $t("page.protocol.apply.options.hub.title"),
      description: $t("page.protocol.apply.options.hub.description"),
    },
  ]
})

const { routerReplaceByKey, route } = useRouterPush()

function navigateToEditorWithContext(protocolUid?: string) {
  const { labUid, projectUid } = route.value.params as {
    labUid?: string
    projectUid?: string
  }

  if (!labUid || !projectUid) {
    return routerReplaceByKey("protocol-editor-playground")
  }

  return routerReplaceByKey("protocol-editor", {
    params: {
      labUid,
      projectUid,
      protocolUid: protocolUid || `protocol-${nanoid()}`,
    },
  })
}

function handleSelectOption(option: ApplyOption) {
  if (option === "scratch") {
    if (props.protocolInfo) {
      const { lab, project, uid } = props.protocolInfo!
      routerReplaceByKey("protocol-editor", {
        params: {
          labUid: lab.uid,
          projectUid: project.uid,
          protocolUid: uid,
        },
      })
    }
    else {
      const { protocolUid } = route.value.params as { protocolUid?: string }
      navigateToEditorWithContext(protocolUid)
    }
    return
  }

  if (option === "hub") {
    routerReplaceByKey("hub")
    return
  }

  selectedOption.value = option
  currentStep.value = 2
}
</script>

<style scoped>
.text-primary {
  color: var(--primary-color);
}

.bg-primary-50 {
  background-color: rgba(var(--primary-color-rgb), 0.1);
}
</style>
