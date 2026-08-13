<template>
  <div
    class="grid grid-cols-[repeat(auto-fit,minmax(240px,1fr))] mx-auto w-full gap-6 px-4"
  >
    <n-card
      v-for="option in applyOptions"
      :key="option.type"
      hoverable
      role="button"
      tabindex="0"
      :aria-label="option.title"
      :data-testid="option.type === 'ai' ? 'protocol-create-ai' : undefined"
      class="create-option-card relative transform cursor-pointer transition-all duration-200 hover:shadow-lg hover:-translate-y-1"
      :class="{ 'create-option-card--featured': option.featured }"
      content-class="flex flex-col items-center"
      @click="handleSelectOption(option.type)"
      @keydown.enter.prevent="handleSelectOption(option.type)"
      @keydown.space.prevent="handleSelectOption(option.type)"
    >
      <n-tag v-if="option.featured" type="info" size="small" round class="absolute right-4 top-4">
        {{ $t("page.protocol.apply.options.ai.recommended") }}
      </n-tag>
      <div class="create-option-icon" :class="{ 'create-option-icon--featured': option.featured }">
        <n-icon :size="option.featured ? 30 : 36">
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
import IconWand from "~icons/tabler/wand"
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
  type: NonNullable<ApplyOption> | "ai"
  icon: Component
  title: string
  description: string
  featured?: boolean
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
    {
      type: "ai",
      icon: IconWand,
      title: $t("page.protocol.apply.options.ai.title"),
      description: $t("page.protocol.apply.options.ai.description"),
      featured: true,
    },
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

function navigateToEditorWithContext(protocolUid?: string, query?: Record<string, string>) {
  const routeParams = route.value.params as {
    labUid?: string
    projectUid?: string
  }
  const labUid = routeParams.labUid || props.projectInfo?.lab_uid
  const projectUid = routeParams.projectUid || props.projectInfo?.uid

  if (!labUid || !projectUid) {
    return routerReplaceByKey("protocol-editor-playground", { query })
  }

  return routerReplaceByKey("protocol-editor", {
    params: {
      labUid,
      projectUid,
      protocolUid: protocolUid || `protocol-${nanoid()}`,
    },
    query,
  })
}

function handleSelectOption(option: NonNullable<ApplyOption> | "ai") {
  if (option === "ai") {
    const { protocolUid } = route.value.params as { protocolUid?: string }
    return navigateToEditorWithContext(protocolUid, {
      package_id: `ai-draft-${nanoid()}`,
      show_ai_create: "true",
    })
  }

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
.create-option-icon {
  display: flex;
  width: 3.5rem;
  height: 3.5rem;
  align-items: center;
  justify-content: center;
  margin-bottom: 0.75rem;
  border: 1px solid rgba(107, 114, 128, 0.12);
  border-radius: 0.875rem;
  color: #4b5563;
  background: #f8fafc;
}

.create-option-icon--featured {
  border-color: rgb(var(--primary-color) / 22%);
  color: rgb(var(--primary-color));
  background: linear-gradient(145deg, rgb(var(--primary-color) / 12%), rgb(14 165 233 / 6%));
  box-shadow: 0 6px 16px rgb(var(--primary-color) / 8%);
}

.create-option-card--featured {
  border-color: rgb(var(--primary-color) / 45%);
  background: linear-gradient(135deg, rgb(var(--primary-color) / 10%), rgb(14 165 233 / 6%));
  box-shadow: 0 10px 28px rgb(var(--primary-color) / 8%);
}

.create-option-card:focus-visible {
  outline: 2px solid rgb(var(--primary-color));
  outline-offset: 3px;
}
</style>
