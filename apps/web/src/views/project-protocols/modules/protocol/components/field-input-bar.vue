<template>
  <div class="field-input-bar">
    <input
      ref="fileInputRef"
      type="file"
      class="hidden"
      multiple
      :accept="FILE_INPUT_ACCEPT"
      @change="handleFileSelect"
    >

    <div class="mb-2 flex items-center gap-2">
      <span class="text-sm text-gray-600">{{ $t("page.protocol.fieldInput.title") }}</span>
      <n-tooltip trigger="hover">
        <template #trigger>
          <n-icon size="16" class="cursor-help text-gray-400">
            <icon-tabler-info-circle />
          </n-icon>
        </template>
        {{ $t("page.protocol.fieldInput.hint") }}
      </n-tooltip>
    </div>

    <div class="flex items-end gap-2">
      <div class="mb-1 flex-shrink-0">
        <n-icon :size="32" class="text-primary">
          <icon-shared-airalogy-logo />
        </n-icon>
      </div>

      <div class="relative flex-1">
        <voice-input-status
          :is-recording="isRecording"
          :is-processing="isProcessingAudio"
          :recording-duration="audioRecorder.recordingDuration"
          class-name="mb-2"
        />

        <n-input
          v-if="!isRecording && !isProcessingAudio"
          v-model:value="inputText"
          type="textarea"
          :placeholder="$t('page.protocol.fieldInput.placeholder')"
          :autosize="{ minRows: 1, maxRows: 3 }"
          :disabled="isProcessing"
          size="medium"
          @keydown="handleKeyDown"
        >
          <template #suffix>
            <div class="flex items-center gap-1">
              <n-tooltip trigger="hover">
                <template #trigger>
                  <n-button
                    quaternary
                    size="small"
                    :disabled="isProcessing"
                    class="voice-button"
                    @click="handleFileButtonClick"
                  >
                    <template #icon>
                      <n-icon size="18">
                        <icon-tabler-paperclip />
                      </n-icon>
                    </template>
                  </n-button>
                </template>
                {{ $t("page.protocol.fieldInput.uploadFile") }}
              </n-tooltip>

              <n-tooltip trigger="hover">
                <template #trigger>
                  <n-button
                    quaternary
                    size="small"
                    :disabled="isProcessing"
                    class="voice-button"
                    @click="handleVoiceInput"
                  >
                    <template #icon>
                      <n-icon size="18">
                        <icon-tabler-microphone />
                      </n-icon>
                    </template>
                  </n-button>
                </template>
                {{ $t("page.protocol.fieldInput.voiceInput") }}
              </n-tooltip>
            </div>
          </template>
        </n-input>
      </div>

      <n-button
        v-if="!isRecording && !isProcessingAudio"
        type="primary"
        :loading="isProcessing"
        :disabled="!canSubmit"
        size="medium"
        class="flex-shrink-0"
        style="height: 3rem;"
        @click="handleSubmit"
      >
        <template #icon>
          <n-icon>
            <icon-tabler-send />
          </n-icon>
        </template>
        {{ $t("common.execute") }}
      </n-button>

      <n-button
        v-if="isRecording"
        type="error"
        size="medium"
        class="flex-shrink-0"
        style="height: 3rem;"
        @click="handleVoiceInput"
      >
        <template #icon>
          <n-icon>
            <icon-tabler-microphone />
          </n-icon>
        </template>
        {{ $t("common.stop") }}
      </n-button>
    </div>

    <div v-if="attachments.length > 0" class="mt-3">
      <div class="mb-2 text-xs text-gray-500">
        {{ $t("page.protocol.fieldInput.attachmentsHint") }}
      </div>

      <div class="flex flex-wrap gap-2">
        <div
          v-for="attachment in attachments"
          :key="attachment.id"
          class="attachment-chip"
        >
          <n-icon :size="16" class="attachment-chip__icon">
            <component :is="getAttachmentIcon(attachment.type)" />
          </n-icon>

          <button
            type="button"
            class="attachment-chip__name"
            :disabled="!attachment.url"
            @click="handlePreviewAttachment(attachment)"
          >
            {{ attachment.name }}
          </button>

          <span class="attachment-chip__meta">
            {{ formatFileSize(attachment.size) }}
          </span>

          <span class="attachment-chip__status" :class="getAttachmentStatusClass(attachment.status)">
            {{ getAttachmentStatusLabel(attachment.status) }}
          </span>

          <n-button
            quaternary
            circle
            size="tiny"
            :disabled="isProcessing"
            @click="removeAttachment(attachment.id)"
          >
            <template #icon>
              <n-icon :size="14">
                <icon-tabler-x />
              </n-icon>
            </template>
          </n-button>
        </div>
      </div>
    </div>

    <div v-if="lastResult" class="mt-2 rounded p-2 text-sm" :class="lastResultClass">
      <div class="whitespace-pre-wrap">
        {{ lastResult }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { RecorderTurn } from "@airalogy/components/chat/providers/recorderTurn"
import { postAddAttachments } from "@/service/api/attachments"
import { baseURL } from "@/service/request"
import { useAuthStore } from "@/store/modules/auth"
import { useAudioRecorder, VoiceInputStatus } from "@airalogy/components"
import { useClosableMessage } from "@airalogy/composables"
import { getFileType } from "@airalogy/shared/utils"
import IconSharedAiralogyLogo from "~icons/shared/airalogy-logo"
import IconTablerFile from "~icons/tabler/file"
import IconTablerFileDescription from "~icons/tabler/file-description"
import IconTablerFileText from "~icons/tabler/file-text"
import IconTablerFileTypePdf from "~icons/tabler/file-type-pdf"
import IconTablerInfoCircle from "~icons/tabler/info-circle"
import IconTablerMicrophone from "~icons/tabler/microphone"
import IconTablerPaperclip from "~icons/tabler/paperclip"
import IconTablerPhoto from "~icons/tabler/photo"
import IconTablerSend from "~icons/tabler/send"
import IconTablerX from "~icons/tabler/x"
import { NButton, NIcon, NInput, NTooltip } from "naive-ui"
import { nanoid } from "nanoid"
import { computed, ref } from "vue"
import { useI18n } from "vue-i18n"

interface Props {
  beginTurn: () => RecorderTurn | undefined
  protocolId: string
}

type FieldInputFileType = "image" | "pdf" | "docx" | "text"
type FieldInputAttachmentStatus = "pending" | "uploading" | "uploaded"

interface FieldInputAttachment {
  id: string
  file: File
  name: string
  size: number
  type: FieldInputFileType
  status: FieldInputAttachmentStatus
  attachmentId?: string
  url?: string
}

const props = defineProps<Props>()
const MAX_ATTACHMENT_SIZE = 10 * 1024 * 1024
const FILE_INPUT_ACCEPT = "image/*,.pdf,.doc,.docx,.txt,.md,.markdown,.csv,.tsv,.json,.log,.yaml,.yml,.xml,.toml"
const DEFAULT_ATTACHMENT_PROMPT = "Please fill the protocol fields using the uploaded attachments."
const WORD_MIME_TYPES = new Set([
  "application/msword",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/vnd.ms-word.document.macroenabled.12",
])
const TEXT_MIME_TYPES = new Set([
  "application/json",
  "application/xml",
  "application/x-yaml",
  "application/yaml",
  "text/csv",
  "text/markdown",
  "text/plain",
  "text/tab-separated-values",
  "text/xml",
])

const authStore = useAuthStore()
const message = useClosableMessage()
const { t } = useI18n()

const inputText = ref("")
const isProcessing = ref(false)
const isProcessingAudio = ref(false)
const lastResult = ref("")
const lastResultSuccess = ref(true)
const fileInputRef = ref<HTMLInputElement | null>(null)
const attachments = ref<FieldInputAttachment[]>([])

const {
  isRecording,
  audioRecorder,
  startRecording,
  stopRecording,
  resetAudioRecorder,
} = useAudioRecorder()

const lastResultClass = computed(() => {
  return lastResultSuccess.value
    ? "bg-green-50 text-green-800 border border-green-200"
    : "bg-red-50 text-red-800 border border-red-200"
})

const canSubmit = computed(() => {
  return !isProcessing.value && (inputText.value.trim().length > 0 || attachments.value.length > 0)
})

async function handleSubmit() {
  if (!canSubmit.value) {
    return
  }

  lastResult.value = ""
  isProcessing.value = true

  try {
    const files = await prepareMessageFiles()
    const content = inputText.value.trim() || DEFAULT_ATTACHMENT_PROMPT
    const endpoint = `${baseURL}/chats/field_input/message`

    const turn = props.beginTurn()
    if (!turn)
      return
    const response = await fetch(endpoint, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Auth-Token": authStore.token || "",
      },
      body: JSON.stringify({
        protocol_id: props.protocolId,
        recorder_target: turn.target,
        message: {
          role: "user",
          content,
          files: files.length > 0 ? files : undefined,
        },
        model: { model_type: 1 },
      }),
    })

    if (!response.ok) {
      const errorText = await response.text()
      console.error("[Field Input Bar] HTTP error:", response.status, errorText)
      throw new Error(`Request failed: ${response.status}`)
    }

    const jsonData = await response.json()
    const feedback = await turn.apply(jsonData.recorder_proposal)
    lastResult.value = feedback
    lastResultSuccess.value = Boolean(feedback)

    inputText.value = ""
    attachments.value = []
  }
  catch (error) {
    console.error("[Field Input Bar] Error:", error)
    lastResultSuccess.value = false
    lastResult.value = t("page.protocol.fieldInput.operationFailed", { message: (error as Error).message })
    message.error(t("page.protocol.fieldInput.operationFailed", { message: (error as Error).message }))
  }
  finally {
    isProcessing.value = false
  }
}

function handleFileButtonClick() {
  if (isProcessing.value) {
    return
  }

  fileInputRef.value?.click()
}

function handleFileSelect(event: Event) {
  const target = event.target as HTMLInputElement | null
  const files = Array.from(target?.files || [])

  if (files.length === 0) {
    return
  }

  const nextAttachments: FieldInputAttachment[] = []

  files.forEach((file) => {
    const resolvedType = resolveAttachmentType(file)
    if (!resolvedType) {
      message.error(t("page.protocol.fieldInput.unsupportedFileType", { name: file.name }))
      return
    }

    if (file.size > MAX_ATTACHMENT_SIZE) {
      message.error(t("page.protocol.fieldInput.fileTooLarge", { name: file.name }))
      return
    }

    nextAttachments.push({
      id: nanoid(),
      file,
      name: file.name,
      size: file.size,
      type: resolvedType,
      status: "pending",
    })
  })

  if (nextAttachments.length > 0) {
    attachments.value = [...attachments.value, ...nextAttachments]
  }

  if (target) {
    target.value = ""
  }
}

function removeAttachment(id: string) {
  attachments.value = attachments.value.filter(attachment => attachment.id !== id)
}

async function prepareMessageFiles() {
  return await Promise.all(attachments.value.map(uploadAttachment))
}

async function uploadAttachment(attachment: FieldInputAttachment) {
  if (attachment.attachmentId) {
    updateAttachment(attachment.id, { status: "uploaded" })
    return {
      id: attachment.attachmentId,
      type: attachment.type,
      file_name: attachment.name,
    }
  }

  updateAttachment(attachment.id, { status: "uploading" })

  const response = await postAddAttachments(attachment.file)
  if (response.error || !response.data?.id) {
    updateAttachment(attachment.id, { status: "pending" })
    throw new Error(t("page.protocol.fieldInput.attachmentUploadFailed", { name: attachment.name }))
  }

  updateAttachment(attachment.id, {
    attachmentId: response.data.id,
    status: "uploaded",
    url: response.data.url,
  })

  return {
    id: response.data.id,
    type: attachment.type,
    file_name: attachment.name,
  }
}

function updateAttachment(id: string, payload: Partial<FieldInputAttachment>) {
  attachments.value = attachments.value.map((attachment) => {
    if (attachment.id !== id) {
      return attachment
    }

    return {
      ...attachment,
      ...payload,
    }
  })
}

function resolveAttachmentType(file: File): FieldInputFileType | null {
  const normalizedType = getFileType(file.name)

  if (file.type.startsWith("image/") || normalizedType === "image") {
    return "image"
  }

  if (file.type === "application/pdf" || normalizedType === "pdf") {
    return "pdf"
  }

  if (WORD_MIME_TYPES.has(file.type) || normalizedType === "word") {
    return "docx"
  }

  if (
    file.type.startsWith("text/")
    || TEXT_MIME_TYPES.has(file.type)
    || normalizedType === "text"
    || normalizedType === "csv"
    || normalizedType === "code"
  ) {
    return "text"
  }

  return null
}

function getAttachmentIcon(type: FieldInputFileType) {
  if (type === "image") {
    return IconTablerPhoto
  }

  if (type === "pdf") {
    return IconTablerFileTypePdf
  }

  if (type === "docx") {
    return IconTablerFileDescription
  }

  if (type === "text") {
    return IconTablerFileText
  }

  return IconTablerFile
}

function getAttachmentStatusLabel(status: FieldInputAttachmentStatus) {
  if (status === "uploading") {
    return t("page.protocol.fieldInput.attachmentUploading")
  }

  if (status === "uploaded") {
    return t("page.protocol.fieldInput.attachmentUploaded")
  }

  return t("page.protocol.fieldInput.attachmentPending")
}

function getAttachmentStatusClass(status: FieldInputAttachmentStatus) {
  if (status === "uploading") {
    return "attachment-chip__status--uploading"
  }

  if (status === "uploaded") {
    return "attachment-chip__status--uploaded"
  }

  return "attachment-chip__status--pending"
}

function handlePreviewAttachment(attachment: FieldInputAttachment) {
  if (!attachment.url) {
    return
  }

  window.open(attachment.url, "_blank", "noopener,noreferrer")
}

function formatFileSize(size: number) {
  if (!size) {
    return "0 B"
  }

  const units = ["B", "KB", "MB", "GB"]
  const exponent = Math.min(Math.floor(Math.log(size) / Math.log(1024)), units.length - 1)
  const value = size / (1024 ** exponent)

  return `${value >= 10 || exponent === 0 ? value.toFixed(0) : value.toFixed(1)} ${units[exponent]}`
}

function handleKeyDown(e: KeyboardEvent) {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault()
    void handleSubmit()
  }
}

async function handleVoiceInput() {
  if (isRecording.value) {
    await stopRecording()
    if (audioRecorder.value.audioBlob) {
      isProcessingAudio.value = true
      try {
        const formData = new FormData()
        formData.append("audio", audioRecorder.value.audioBlob)

        const endpoint = `${baseURL}/chats/stt/message`
        const response = await fetch(endpoint, {
          method: "POST",
          headers: {
            "Auth-Token": authStore.token || "",
          },
          body: formData,
        })

        if (!response.ok) {
          throw new Error(`STT Request failed: ${response.status}`)
        }

        const data = await response.json()
        const text = data.text || data.content || data.message || data.transcript || (typeof data === "string" ? data : "")

        if (text) {
          inputText.value = (inputText.value ? `${inputText.value} ` : "") + text
        }
        else {
          console.warn("STT Response did not contain expected text field:", data)
          message.warning(t("page.protocol.fieldInput.transcriptionMissing"))
        }
      }
      catch (error) {
        console.error("STT Error:", error)
        message.error(t("page.protocol.fieldInput.transcriptionFailed"))
      }
      finally {
        isProcessingAudio.value = false
        resetAudioRecorder()
      }
    }
  }
  else {
    await startRecording()
  }
}
</script>

<style scoped lang="sass">
.field-input-bar
  padding: 12px
  background-color: #f9fafb
  border-radius: 8px
  border: 1px solid #e5e7eb

.voice-button
  height: fit-content !important
  padding: 4px !important
  border-radius: 4px !important

.attachment-chip
  display: inline-flex
  align-items: center
  gap: 8px
  max-width: 100%
  padding: 6px 8px
  background-color: #ffffff
  border: 1px solid #dbe3f0
  border-radius: 9999px

.attachment-chip__icon
  color: #4f46e5

.attachment-chip__name
  max-width: 200px
  overflow: hidden
  white-space: nowrap
  text-overflow: ellipsis
  background: transparent
  border: none
  padding: 0
  font-size: 12px
  color: #111827
  cursor: pointer

  &:disabled
    color: #111827
    cursor: default

.attachment-chip__meta
  font-size: 12px
  color: #6b7280

.attachment-chip__status
  font-size: 11px
  line-height: 1
  padding: 4px 6px
  border-radius: 9999px

.attachment-chip__status--pending
  background-color: #eef2ff
  color: #4338ca

.attachment-chip__status--uploading
  background-color: #eff6ff
  color: #2563eb

.attachment-chip__status--uploaded
  background-color: #ecfdf5
  color: #059669

.animate-pulse
  animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite

@keyframes pulse
  0%, 100%
    opacity: 1
  50%
    opacity: 0.3
</style>
