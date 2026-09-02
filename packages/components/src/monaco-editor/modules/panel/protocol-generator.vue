<template>
  <div class="protocol-generator size-full flex flex-col gap-4 p-4">
    <div class="generator-toolbar">
      <h3 class="text-base font-semibold">
        {{ $t("editor.protocolGenerator.title") }}
      </h3>
      <n-select v-model:value="selectedModel" :options="modelOptions" class="w-32" size="small" />
    </div>

    <div class="generation-step" :class="{ 'step-completed': aimdGenerated }">
      <div class="step-header">
        <div class="step-info">
          <div class="step-title">
            {{ $t("editor.protocolGenerator.stepTitle") }}
          </div>
          <div class="step-description">
            {{ $t("editor.protocolGenerator.description") }}
          </div>
        </div>
      </div>

      <div class="step-content">
        <div v-if="hasExistingAimd" class="step-hint mb-3">
          {{ $t("editor.protocolGenerator.replaceHint") }}
        </div>

        <div class="instruction-toolbar">
          <div class="instruction-meta">
            <div class="instruction-label">
              {{ $t("editor.protocolGenerator.instructionLabel") }}
            </div>
            <div class="instruction-caption">
              {{ $t("editor.protocolGenerator.instructionCaption") }}
            </div>
          </div>

          <div v-if="props.extractInstructionFile" class="instruction-actions">
            <input
              ref="fileInputRef"
              class="hidden"
              type="file"
              multiple
              :accept="FILE_ACCEPT"
              @change="handleFileInputChange"
            >

            <n-button
              size="small"
              secondary
              :loading="isExtractingFile"
              :disabled="isBusy"
              @click="openFilePicker"
            >
              <template #icon>
                <n-icon>
                  <icon-tabler-upload />
                </n-icon>
              </template>
              {{ $t("editor.protocolGenerator.addFromFile") }}
            </n-button>
          </div>
        </div>

        <div v-if="importedSources.length" class="imported-sources">
          <span
            v-for="source in importedSources"
            :key="source.id"
            class="source-pill"
          >
            {{ source.filename }}
            <span v-if="source.wasTrimmed" class="source-pill__flag">{{ $t("editor.protocolGenerator.trimmed") }}</span>
          </span>
        </div>

        <n-input
          v-model:value="instruction"
          data-testid="ai-protocol-requirements"
          class="generator-textarea"
          type="textarea"
          :placeholder="placeholderText"
          :rows="12"
          :disabled="isBusy"
          :maxlength="MAX_INSTRUCTION_LENGTH"
          show-count
        />

        <n-button
          type="primary"
          data-testid="ai-protocol-generate"
          :loading="isGenerating"
          :disabled="!instruction.trim() || isBusy || props.disabled"
          class="mt-2 w-full"
          @click="handleGenerateProtocol"
        >
          <template #icon>
            <n-icon>
              <icon-tabler-sparkles />
            </n-icon>
          </template>
          {{ $t("editor.protocolGenerator.generate") }}
        </n-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { ChatModelConfig } from "@airalogy/shared"
import { ChatModel } from "@airalogy/shared"
import { $t } from "@airalogy/shared/locales"
import IconTablerSparkles from "~icons/tabler/sparkles"
import IconTablerUpload from "~icons/tabler/upload"
import { NButton, NIcon, NInput, NSelect, useMessage } from "naive-ui"
import { computed, ref, watch } from "vue"

interface ExtractedInstructionFile {
  filename: string
  text: string
  was_trimmed: boolean
  content_type: string
}

interface ImportedSource {
  id: string
  filename: string
  wasTrimmed: boolean
}

interface IProps {
  generateAimd?: (
    payload: { instruction: string, model: ChatModelConfig },
    requestId?: string,
  ) => Promise<{ data: string | null, error: any }>
  generateModel?: (
    payload: { protocol_aimd: string, model: ChatModelConfig },
    requestId?: string,
  ) => Promise<{ data: string | null, error: any }>
  generateAssigner?: (
    payload: { protocol_aimd: string, protocol_model: string, model: ChatModelConfig },
    requestId?: string,
  ) => Promise<{ data: string | null, error: any }>
  extractInstructionFile?: (
    file: File,
  ) => Promise<{ data: ExtractedInstructionFile | null, error: any }>
  onSaveFile?: (content: string, filename: string, language: string) => void | Promise<void>
  currentAimdContent?: string
  currentModelContent?: string
  initialInstruction?: string
  disabled?: boolean
}

const props = withDefaults(defineProps<IProps>(), {
  generateAimd: () => Promise.reject(new Error("generateAimd not provided")),
  generateModel: () => Promise.reject(new Error("generateModel not provided")),
  generateAssigner: () => Promise.reject(new Error("generateAssigner not provided")),
  extractInstructionFile: undefined,
  initialInstruction: "",
  disabled: false,
})

const MAX_INSTRUCTION_LENGTH = 20000
const FILE_ACCEPT = ".txt,.md,.markdown,.pdf,.doc,.docx"

const message = useMessage()

const modelOptions = [
  { label: "Basic", value: ChatModel.BASIC },
  { label: "Plus", value: ChatModel.PLUS },
  { label: "Pro", value: ChatModel.PRO },
]
const selectedModel = ref<number>(ChatModel.BASIC)

const isGenerating = ref(false)
const isExtractingFile = ref(false)
const instruction = ref(props.initialInstruction.slice(0, MAX_INSTRUCTION_LENGTH))
const lastInitialInstruction = ref(instruction.value)
const fileInputRef = ref<HTMLInputElement | null>(null)
const importedSources = ref<ImportedSource[]>([])
const placeholderText = computed(() => $t("editor.protocolGenerator.placeholder"))

const generatedAimd = ref<string | null>(null)
const aimdGenerated = computed(() => generatedAimd.value !== null)
const hasExistingAimd = computed(() => Boolean(props.currentAimdContent?.trim()))
const isBusy = computed(() => isGenerating.value || isExtractingFile.value)

watch(() => props.initialInstruction, (value) => {
  const nextValue = value.slice(0, MAX_INSTRUCTION_LENGTH)
  if (!instruction.value.trim() || instruction.value === lastInitialInstruction.value) {
    instruction.value = nextValue
  }
  lastInitialInstruction.value = nextValue
})

function getChatModelConfig(): ChatModelConfig {
  return {
    model_type: selectedModel.value as 1 | 2 | 3,
    enable_thinking: false,
    enable_search: false,
  }
}

function openFilePicker() {
  if (isBusy.value) {
    return
  }

  fileInputRef.value?.click()
}

function buildImportedInstructionBlock(file: ExtractedInstructionFile) {
  return `Reference file: ${file.filename}\n${file.text.trim()}`
}

function appendInstructionBlock(block: string) {
  const separator = instruction.value.trim() ? "\n\n" : ""
  const availableChars = MAX_INSTRUCTION_LENGTH - instruction.value.length - separator.length

  if (availableChars <= 0) {
    return { appended: false, truncatedByLimit: true }
  }

  let nextBlock = block
  let truncatedByLimit = false

  if (nextBlock.length > availableChars) {
    truncatedByLimit = true
    const notice = "\n\n[NOTE: Appended content was truncated to fit the instruction limit.]"

    if (availableChars <= notice.length) {
      nextBlock = nextBlock.slice(0, availableChars)
    }
    else {
      const bodyLimit = availableChars - notice.length
      nextBlock = `${nextBlock.slice(0, bodyLimit)}${notice}`
    }
  }

  instruction.value = `${instruction.value}${separator}${nextBlock}`
  return { appended: true, truncatedByLimit }
}

function upsertImportedSource(file: ExtractedInstructionFile) {
  const existingIndex = importedSources.value.findIndex(
    source => source.filename === file.filename,
  )

  const nextSource: ImportedSource = {
    id: file.filename,
    filename: file.filename,
    wasTrimmed: file.was_trimmed,
  }

  if (existingIndex >= 0) {
    importedSources.value.splice(existingIndex, 1, nextSource)
    return
  }

  importedSources.value.push(nextSource)
}

async function handleFileInputChange(event: Event) {
  const target = event.target as HTMLInputElement
  const files = Array.from(target.files || [])
  target.value = ""

  if (!files.length || !props.extractInstructionFile) {
    return
  }

  isExtractingFile.value = true

  let importedCount = 0
  let trimmedCount = 0
  let truncatedByLimitCount = 0

  try {
    for (const file of files) {
      const { data, error } = await props.extractInstructionFile(file)
      if (error || !data?.text) {
        throw new Error(error?.message || $t("editor.protocolGenerator.extractFailed", { filename: file.name }))
      }

      const { appended, truncatedByLimit } = appendInstructionBlock(
        buildImportedInstructionBlock(data),
      )

      if (!appended) {
        throw new Error($t("editor.protocolGenerator.limitReached"))
      }

      upsertImportedSource(data)
      importedCount += 1

      if (data.was_trimmed) {
        trimmedCount += 1
      }

      if (truncatedByLimit) {
        truncatedByLimitCount += 1
      }
    }

    if (importedCount === 1) {
      message.success($t("editor.protocolGenerator.importedOne", { filename: files[0]?.name || "" }))
    }
    else if (importedCount > 1) {
      message.success($t("editor.protocolGenerator.importedMany", { count: importedCount }))
    }

    if (trimmedCount > 0) {
      message.info($t("editor.protocolGenerator.trimmedFiles", { count: trimmedCount }))
    }

    if (truncatedByLimitCount > 0) {
      message.warning($t("editor.protocolGenerator.shortenedFiles"))
    }
  }
  catch (error: any) {
    message.error(error.message || $t("editor.protocolGenerator.extractError"))
  }
  finally {
    isExtractingFile.value = false
  }
}

async function handleGenerateProtocol() {
  if (!instruction.value.trim()) {
    message.warning($t("editor.protocolGenerator.enterInstruction"))
    return
  }

  try {
    isGenerating.value = true

    const { data, error } = await props.generateAimd({
      instruction: instruction.value,
      model: getChatModelConfig(),
    })

    if (error || !data) {
      throw new Error(error?.message || $t("editor.protocolGenerator.generateFailed"))
    }

    generatedAimd.value = data
    if (props.onSaveFile) {
      await props.onSaveFile(data, "protocol.aimd", "aimd")
    }
    message.success($t("editor.protocolGenerator.generated"))
  }
  catch (error: any) {
    message.error(error.message || $t("editor.protocolGenerator.generateFailed"))
  }

  isGenerating.value = false
}
</script>

<style lang="sass" scoped>
.protocol-generator
  height: 100%
  min-height: 0
  overflow: hidden

.generator-toolbar
  display: flex
  align-items: center
  justify-content: space-between
  gap: 12px
  flex-shrink: 0

.generation-step
  display: flex
  flex: 1
  flex-direction: column
  min-height: 0
  border: 1px solid #e5e7eb
  border-radius: 12px
  padding: 18px
  transition: all 0.3s ease

  &.step-completed
    border-color: #10b981
    background-color: rgba(16, 185, 129, 0.05)

.step-header
  display: flex
  align-items: flex-start
  justify-content: space-between
  gap: 12px
  margin-bottom: 16px
  flex-shrink: 0

.step-info
  flex: 1

.step-title
  font-size: 14px
  font-weight: 600
  margin-bottom: 4px

.step-description
  font-size: 13px
  line-height: 1.5
  color: #6b7280

.step-content
  display: flex
  flex: 1
  flex-direction: column
  min-height: 0

.instruction-toolbar
  display: flex
  align-items: flex-start
  justify-content: space-between
  gap: 12px
  margin-bottom: 12px
  flex-shrink: 0

.instruction-meta
  min-width: 0

.instruction-label
  font-size: 13px
  font-weight: 600
  margin-bottom: 4px

.instruction-caption
  font-size: 12px
  line-height: 1.5
  color: #6b7280

.instruction-actions
  flex-shrink: 0

.imported-sources
  display: flex
  flex-wrap: wrap
  gap: 8px
  margin-bottom: 12px
  flex-shrink: 0

.source-pill
  display: inline-flex
  align-items: center
  gap: 6px
  padding: 6px 10px
  border-radius: 999px
  background-color: #f3f4f6
  border: 1px solid rgba(148, 163, 184, 0.25)
  font-size: 12px
  line-height: 1
  color: #4b5563

.source-pill__flag
  color: #b45309

.step-hint
  padding: 12px 14px
  background-color: #f3f4f6
  border: 1px solid rgba(148, 163, 184, 0.25)
  border-radius: 10px
  font-size: 13px
  color: #6b7280

.generator-textarea
  flex: 1
  min-height: 0

.generator-textarea :deep(.n-input)
  height: 100%

.generator-textarea :deep(.n-input-wrapper)
  height: 100%
  align-items: stretch
  padding: 12px 14px
  border-radius: 10px

.generator-textarea :deep(.n-input__textarea),
.generator-textarea :deep(.n-input__textarea-el),
.generator-textarea :deep(.n-input__textarea-mirror)
  min-height: 100% !important

.generator-textarea :deep(.n-input__textarea-el)
  line-height: 1.6

// Dark theme
:global(.dark) .generation-step
  border-color: #374151

  &.step-completed
    border-color: #059669
    background-color: rgba(5, 150, 105, 0.1)

:global(.dark) .step-description
  color: #9ca3af

:global(.dark) .instruction-caption
  color: #9ca3af

:global(.dark) .source-pill
  background-color: #111827
  border-color: rgba(71, 85, 105, 0.45)
  color: #d1d5db

:global(.dark) .source-pill__flag
  color: #fbbf24

:global(.dark) .step-hint
  background-color: #1f2937
  border-color: rgba(71, 85, 105, 0.45)
  color: #9ca3af
</style>
