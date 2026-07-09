<template>
  <div
    class="grid grid-cols-[repeat(auto-fit,minmax(240px,1fr))] mx-auto w-full gap-6 px-4"
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

  <import-aira-archive-modal
    ref="airaImportModalRef"
    :project="props.projectInfo"
    :show-button="false"
    @imported="handleImportArchive"
  />
</template>

<script setup lang="ts">
import type { ImportAiraArchiveResponse } from "@/service/api/project-protocols"
import type { ProtocolModels } from "@airalogy/shared/types/models"
import type { ApplyOption } from "./composables/useApplyProtocolState"
import { $t } from "@/locales"
import ImportAiraArchiveModal from "@/views/project-protocols/modules/import-aira-archive-modal.vue"
import HubIcon from "~icons/local/hub"
import IconFile from "~icons/tabler/file"
import IconFileImport from "~icons/tabler/file-import"
import IconFileZip from "~icons/tabler/file-zip"
import IconReportSearch from "~icons/tabler/report-search"
import { nanoid } from "nanoid"
import { useRouterPush } from "../../composables/useRouterPush"
import { useApplyProtocol } from "./composables/useApplyProtocolState"

interface IProps {
  protocolInfo?: ProtocolModels.ProjectProtocolInfo | null
  projectInfo?: Api.Project.MyProjectInfo | null
}

const props = withDefaults(defineProps<IProps>(), {
  protocolInfo: undefined,
  projectInfo: null,
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
    defaultApplyOptions.value[0]!,
    {
      type: "upload-aira",
      icon: IconFileImport,
      title: $t("page.protocol.apply.options.uploadAira.title"),
      description: $t("page.protocol.apply.options.uploadAira.description"),
    },
    defaultApplyOptions.value[1]!,
    defaultApplyOptions.value[2]!,
    {
      type: "hub",
      icon: HubIcon,
      title: $t("page.protocol.apply.options.hub.title"),
      description: $t("page.protocol.apply.options.hub.description"),
    },
  ]
})

const { routerPushByKey, routerReplaceByKey, route } = useRouterPush()
const airaImportModalRef = ref<InstanceType<typeof ImportAiraArchiveModal> | null>(null)

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

  if (option === "upload-aira") {
    airaImportModalRef.value?.open()
    return
  }

  selectedOption.value = option
  currentStep.value = 2
}

async function handleImportArchive(result: ImportAiraArchiveResponse) {
  const importedProtocol = result.protocols[0]
  if (!importedProtocol) {
    return
  }

  await routerPushByKey("protocol-info", {
    params: {
      labUid: importedProtocol.lab_uid,
      projectUid: importedProtocol.project_uid,
      protocolUid: importedProtocol.uid,
    },
  })
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
