<template>
  <n-button size="small" type="primary" secondary @click="open">
    {{ $t("page.research.provideExternalResult") }}
  </n-button>

  <n-modal
    v-model:show="visible"
    preset="card"
    class="research-signal-modal"
    :title="$t('page.research.provideExternalResult')"
    :mask-closable="false"
    @after-leave="reset"
  >
    <n-alert type="warning" class="mb-4">
      {{ $t("page.research.signalResponsibility") }}
    </n-alert>

    <template v-if="!preview">
      <div class="signal-context mb-4">
        <span class="aira-type-meta">{{ $t("page.research.expectedEvent") }}</span>
        <strong class="aira-type-label">{{ event.expected_event_type }}</strong>
      </div>
      <n-form v-if="schemaProperties.length" label-placement="top">
        <n-form-item
          v-for="property in schemaProperties"
          :key="property.name"
          :label="propertyLabel(property.name)"
          :required="property.required"
        >
          <n-select
            v-if="property.enumValues.length"
            v-model:value="payload[property.name]"
            :options="property.enumValues.map(value => ({ label: String(value), value }))"
          />
          <n-input-number
            v-else-if="property.type === 'integer' || property.type === 'number'"
            v-model:value="payload[property.name]"
            :precision="property.type === 'integer' ? 0 : undefined"
          />
          <n-switch
            v-else-if="property.type === 'boolean'"
            v-model:value="payload[property.name]"
          />
          <n-input v-else v-model:value="payload[property.name]" />
        </n-form-item>
      </n-form>
      <n-form v-else label-placement="top">
        <n-form-item :label="$t('page.research.eventPayload')" required>
          <n-input
            v-model:value="rawPayload"
            type="textarea"
            :autosize="{ minRows: 5, maxRows: 14 }"
            placeholder="{}"
          />
        </n-form-item>
      </n-form>
    </template>

    <template v-else>
      <n-alert type="info">
        {{ $t("page.research.signalPreviewHint") }}
      </n-alert>
      <div class="signal-preview mt-4">
        <div class="aira-type-eyebrow">
          {{ $t("page.research.externalSignal") }}
        </div>
        <h3 class="aira-type-card-title mb-0 mt-1">
          {{ event.expected_event_type }}
        </h3>
        <pre>{{ formattedPayload }}</pre>
      </div>
    </template>

    <template #footer>
      <div class="flex justify-end gap-2">
        <n-button @click="preview ? (preview = null) : (visible = false)">
          {{ preview ? $t("page.research.backToEdit") : $t("common.cancel") }}
        </n-button>
        <n-button
          v-if="!preview"
          type="primary"
          :disabled="!requiredValuesComplete"
          :loading="submitting"
          @click="previewSignal"
        >
          {{ $t("page.research.previewSignal") }}
        </n-button>
        <n-button v-else type="primary" :loading="submitting" @click="confirmSignal">
          {{ $t("page.research.confirmSignal") }}
        </n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import type { DigitalActionPreview, WaitEventSignalDraft } from "@/service/api/research-actions"
import type { ResearchWaitEvent } from "@/service/api/research-tasks"
import { previewWaitEventSignal, signalWaitEvent } from "@/service/api/research-actions"
import { $t } from "@airalogy/shared/locales"

const props = defineProps<{ event: ResearchWaitEvent }>()
const emit = defineEmits<{ signaled: [] }>()

interface SchemaProperty {
  name: string
  type: string
  required: boolean
  enumValues: Array<string | number>
}

const visible = ref(false)
const submitting = ref(false)
const preview = ref<DigitalActionPreview<WaitEventSignalDraft> | null>(null)
const payload = reactive<Record<string, any>>({})
const rawPayload = ref("{}")

const schemaProperties = computed<SchemaProperty[]>(() => {
  const properties = props.event.payload_schema?.properties
  if (!properties || typeof properties !== "object")
    return []
  const required = new Set(
    Array.isArray(props.event.payload_schema.required)
      ? props.event.payload_schema.required.map(String)
      : [],
  )
  return Object.entries(properties).map(([name, rawDefinition]) => {
    const definition
      = rawDefinition && typeof rawDefinition === "object"
        ? (rawDefinition as Record<string, any>)
        : {}
    return {
      name,
      type: String(definition.type || "string"),
      required: required.has(name),
      enumValues: Array.isArray(definition.enum) ? definition.enum : [],
    }
  })
})

const requiredValuesComplete = computed(() =>
  schemaProperties.value.length
    ? schemaProperties.value.every((property) => {
      if (!property.required)
        return true
      const value = payload[property.name]
      return value !== null && value !== undefined && value !== ""
    })
    : Boolean(rawPayload.value.trim()),
)

const formattedPayload = computed(() =>
  JSON.stringify(preview.value?.command.payload || {}, null, 2),
)
const propertyLabels = computed<Record<string, string>>(() => ({
  data_asset_id: $t("page.research.payloadDataAssetId"),
  version: $t("page.research.payloadVersion"),
  file_id: $t("page.research.payloadFileId"),
  checksum: $t("page.research.payloadChecksum"),
  result_uri: $t("page.research.payloadResultUri"),
  status: $t("page.research.payloadStatus"),
}))

function propertyLabel(name: string) {
  return propertyLabels.value[name] || name
}

function initializePayload() {
  for (const key of Object.keys(payload)) delete payload[key]
  for (const property of schemaProperties.value) {
    if (property.enumValues.length)
      payload[property.name] = property.enumValues[0]
    else if (property.type === "boolean")
      payload[property.name] = false
    else if (property.type === "integer" || property.type === "number")
      payload[property.name] = null
    else payload[property.name] = ""
  }
  rawPayload.value = "{}"
}

function open() {
  initializePayload()
  visible.value = true
}

function reset() {
  preview.value = null
  initializePayload()
}

function normalizedPayload() {
  if (!schemaProperties.value.length) {
    try {
      const parsed = JSON.parse(rawPayload.value || "{}")
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed))
        throw new Error("Payload must be an object")
      return parsed as Record<string, unknown>
    }
    catch {
      window.$message?.error($t("page.research.invalidEventPayload"))
      return null
    }
  }
  return Object.fromEntries(
    schemaProperties.value
      .filter(property => property.required || payload[property.name] !== "")
      .map(property => [property.name, payload[property.name]]),
  )
}

async function previewSignal() {
  const normalized = normalizedPayload()
  if (!normalized)
    return
  submitting.value = true
  try {
    preview.value = await previewWaitEventSignal(props.event.id, {
      expected_revision: props.event.revision,
      event_type: props.event.expected_event_type,
      payload: normalized,
    })
  }
  finally {
    submitting.value = false
  }
}

async function confirmSignal() {
  if (!preview.value)
    return
  submitting.value = true
  try {
    await signalWaitEvent(props.event.id, {
      expected_revision: props.event.revision,
      event_type: props.event.expected_event_type,
      payload: preview.value.command.payload,
      preview_digest: preview.value.preview_digest,
    })
    visible.value = false
    window.$message?.success($t("page.research.signalReceived"))
    emit("signaled")
  }
  finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.signal-context,
.signal-preview {
  border: 1px solid rgb(226 232 240);
  border-radius: 0.75rem;
  background: rgb(248 250 252);
  padding: 0.875rem;
}

.signal-context {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.signal-preview pre {
  margin: 0.75rem 0 0;
  overflow: auto;
  border-radius: 0.625rem;
  background: rgb(15 23 42);
  color: rgb(226 232 240);
  font-size: 0.75rem;
  line-height: 1.55;
  padding: 0.75rem;
}

:global(.research-signal-modal) {
  width: min(38rem, calc(100vw - 2rem));
}
</style>
