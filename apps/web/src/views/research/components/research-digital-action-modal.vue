<template>
  <n-button secondary @click="open">
    {{ $t("page.research.addDigitalAction") }}
  </n-button>

  <n-modal
    v-model:show="visible"
    preset="card"
    class="research-digital-modal"
    :title="$t('page.research.addDigitalAction')"
    :mask-closable="false"
    @after-leave="reset"
  >
    <template v-if="!preview">
      <n-tabs v-model:value="mode" type="segment" animated>
        <n-tab-pane name="tool" :tab="$t('page.research.toolAction')">
          <n-alert type="info" class="mb-4">
            {{ $t("page.research.toolActionHint") }}
          </n-alert>
          <n-form label-placement="top">
            <n-form-item :label="$t('page.research.researchTool')" required>
              <n-select
                v-model:value="toolDraft.tool_key"
                :options="toolOptions"
                :loading="toolsLoading"
                :placeholder="$t('page.research.selectTool')"
              />
              <template #feedback>
                {{ selectedTool?.description || $t("page.research.noToolsAvailable") }}
              </template>
            </n-form-item>
            <n-form-item :label="$t('page.research.searchQuery')" required>
              <n-input
                v-model:value="toolQuery"
                :placeholder="$t('page.research.searchQueryPlaceholder')"
              />
            </n-form-item>
            <n-form-item :label="$t('page.research.resultLimit')">
              <n-input-number v-model:value="toolLimit" :min="1" :max="50" />
            </n-form-item>
            <n-form-item :label="$t('page.research.actionTitle')">
              <n-input v-model:value="toolDraft.title" />
            </n-form-item>
            <n-form-item :label="$t('page.research.actionDescription')">
              <n-input
                v-model:value="toolDraft.description"
                type="textarea"
                :autosize="{ minRows: 2, maxRows: 6 }"
              />
            </n-form-item>
          </n-form>
        </n-tab-pane>

        <n-tab-pane name="wait" :tab="$t('page.research.waitEventAction')">
          <n-alert type="warning" class="mb-4">
            {{ $t("page.research.waitEventHint") }}
          </n-alert>
          <n-form label-placement="top">
            <n-form-item :label="$t('page.research.waitFor')" required>
              <n-select v-model:value="waitPreset" :options="waitPresetOptions" />
            </n-form-item>
            <n-form-item :label="$t('page.research.actionTitle')" required>
              <n-input
                v-model:value="waitDraft.title"
                :placeholder="$t('page.research.waitTitlePlaceholder')"
              />
            </n-form-item>
            <n-form-item :label="$t('page.research.actionDescription')">
              <n-input
                v-model:value="waitDraft.description"
                type="textarea"
                :autosize="{ minRows: 2, maxRows: 6 }"
              />
            </n-form-item>
            <n-form-item :label="$t('page.research.dueOptional')">
              <n-date-picker
                v-model:value="waitDueAt"
                type="datetime"
                clearable
                :is-date-disabled="disablePastDate"
              />
            </n-form-item>
          </n-form>
        </n-tab-pane>
      </n-tabs>
    </template>

    <template v-else>
      <n-alert type="info">
        {{ $t("page.research.digitalActionPreviewHint") }}
      </n-alert>
      <div class="digital-preview mt-4">
        <div class="aira-type-eyebrow">
          {{ $t("page.research.saveDestination") }}
        </div>
        <h3 class="aira-type-card-title mb-0 mt-1">
          {{ preview.destination.task.title }} ·
          {{ $t("page.research.runNumber", { number: preview.destination.run.number }) }}
        </h3>
        <template v-if="previewKind === 'tool'">
          <div class="mt-4 flex flex-wrap items-center gap-2">
            <n-tag type="info" round>
              {{ preview.tool?.name }}
            </n-tag>
            <span class="aira-type-meta">v{{ preview.tool?.version }}</span>
          </div>
          <p class="aira-type-body aira-text-secondary mb-0 mt-3">
            {{
              $t("page.research.queryPreview", {
                query: String(preview.command.arguments?.query || ""),
              })
            }}
          </p>
          <p class="aira-type-meta mb-0 mt-2">
            {{ $t("page.research.toolResultsStayDraft") }}
          </p>
        </template>
        <template v-else>
          <div class="mt-4 flex flex-wrap items-center gap-2">
            <n-tag type="warning" round>
              {{ $t("page.research.waitEventAction") }}
            </n-tag>
            <span class="aira-type-meta">{{ String(preview.command.expected_event_type) }}</span>
          </div>
          <dl class="digital-preview__facts mt-3">
            <div>
              <dt>{{ $t("page.research.eventKey") }}</dt>
              <dd>{{ String(preview.command.event_key) }}</dd>
            </div>
            <div v-if="preview.command.due_at">
              <dt>{{ $t("page.research.due") }}</dt>
              <dd><n-time :time="new Date(String(preview.command.due_at))" /></dd>
            </div>
          </dl>
          <p class="aira-type-meta mb-0 mt-3">
            {{ $t("page.research.waitPausesRun") }}
          </p>
        </template>
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
          :disabled="!canPreview"
          :loading="submitting"
          @click="previewAction"
        >
          {{ $t("page.research.previewAction") }}
        </n-button>
        <n-button v-else type="primary" :loading="submitting" @click="confirmAction">
          {{ $t("page.research.confirmDigitalAction") }}
        </n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import type {
  DigitalActionPreview,
  ResearchToolDefinition,
  ToolActionDraft,
  WaitActionDraft,
} from "@/service/api/research-actions"
import {
  createToolAction,
  createWaitAction,
  fetchResearchTools,
  previewToolAction,
  previewWaitAction,
} from "@/service/api/research-actions"
import { $t } from "@airalogy/shared/locales"
import { nanoid } from "nanoid"

const props = defineProps<{ taskId: string }>()
const emit = defineEmits<{ created: [] }>()

type Mode = "tool" | "wait"
type WaitPreset = "data_asset" | "research_file" | "external_service"

const visible = ref(false)
const mode = ref<Mode>("tool")
const previewKind = ref<Mode>("tool")
const preview = ref<DigitalActionPreview<any> | null>(null)
const submitting = ref(false)
const toolsLoading = ref(false)
const tools = ref<ResearchToolDefinition[]>([])
const toolQuery = ref("")
const toolLimit = ref(20)
const waitPreset = ref<WaitPreset>("data_asset")
const waitDueAt = ref<number | null>(null)

const toolDraft = reactive<ToolActionDraft>({
  tool_key: "",
  arguments: {},
  title: "",
  description: "",
  idempotency_key: "",
})
const waitDraft = reactive<WaitActionDraft>({
  title: "",
  description: "",
  event_key: "",
  expected_event_type: "",
  payload_schema: {},
  due_at: null,
  idempotency_key: "",
})

const waitDefinitions: Record<WaitPreset, { eventType: string, schema: Record<string, unknown> }>
  = {
    data_asset: {
      eventType: "data_asset.ready",
      schema: {
        type: "object",
        additionalProperties: false,
        required: ["data_asset_id", "version"],
        properties: {
          data_asset_id: { type: "string", minLength: 1 },
          version: { type: "integer", minimum: 1 },
        },
      },
    },
    research_file: {
      eventType: "research_file.received",
      schema: {
        type: "object",
        additionalProperties: false,
        required: ["file_id"],
        properties: {
          file_id: { type: "string", minLength: 1 },
          checksum: { type: "string" },
        },
      },
    },
    external_service: {
      eventType: "external_service.finished",
      schema: {
        type: "object",
        additionalProperties: false,
        required: ["result_uri", "status"],
        properties: {
          result_uri: { type: "string", minLength: 1 },
          status: { type: "string", enum: ["completed", "failed"] },
        },
      },
    },
  }

const toolOptions = computed(() =>
  tools.value.map(item => ({
    label: `${item.name} · v${item.version}`,
    value: item.key,
    disabled: !item.available,
  })),
)
const selectedTool = computed(() => tools.value.find(item => item.key === toolDraft.tool_key))
const waitPresetOptions = computed(() => [
  { label: $t("page.research.waitDataAsset"), value: "data_asset" },
  { label: $t("page.research.waitResearchFile"), value: "research_file" },
  { label: $t("page.research.waitExternalService"), value: "external_service" },
])
const canPreview = computed(() =>
  mode.value === "tool"
    ? Boolean(toolDraft.tool_key && toolQuery.value.trim())
    : Boolean(waitDraft.title.trim() && (!waitDueAt.value || waitDueAt.value > Date.now())),
)

async function loadTools() {
  toolsLoading.value = true
  try {
    tools.value = (await fetchResearchTools(props.taskId)).tools
    toolDraft.tool_key ||= tools.value.find(item => item.available)?.key || ""
  }
  finally {
    toolsLoading.value = false
  }
}

function applyWaitPreset() {
  const definition = waitDefinitions[waitPreset.value]
  waitDraft.expected_event_type = definition.eventType
  waitDraft.payload_schema = definition.schema
}

function open() {
  visible.value = true
  if (!tools.value.length)
    void loadTools()
}

function reset() {
  preview.value = null
  mode.value = "tool"
  previewKind.value = "tool"
  toolQuery.value = ""
  toolLimit.value = 20
  toolDraft.title = ""
  toolDraft.description = ""
  toolDraft.idempotency_key = ""
  waitPreset.value = "data_asset"
  waitDueAt.value = null
  waitDraft.title = ""
  waitDraft.description = ""
  waitDraft.event_key = ""
  waitDraft.idempotency_key = ""
  waitDraft.due_at = null
  applyWaitPreset()
}

function disablePastDate(timestamp: number) {
  return timestamp < new Date().setHours(0, 0, 0, 0)
}

async function previewAction() {
  if (!canPreview.value)
    return
  submitting.value = true
  previewKind.value = mode.value
  try {
    if (mode.value === "tool") {
      toolDraft.arguments = { query: toolQuery.value.trim(), limit: toolLimit.value }
      toolDraft.idempotency_key ||= `tool-${nanoid(16)}`
      preview.value = await previewToolAction(props.taskId, { ...toolDraft })
    }
    else {
      applyWaitPreset()
      waitDraft.event_key ||= `research.wait.${nanoid(16)}`
      waitDraft.idempotency_key ||= `wait-${nanoid(16)}`
      waitDraft.due_at = waitDueAt.value ? new Date(waitDueAt.value).toISOString() : null
      preview.value = await previewWaitAction(props.taskId, { ...waitDraft })
    }
  }
  finally {
    submitting.value = false
  }
}

async function confirmAction() {
  if (!preview.value)
    return
  submitting.value = true
  try {
    if (previewKind.value === "tool") {
      await createToolAction(props.taskId, {
        ...toolDraft,
        preview_digest: preview.value.preview_digest,
      })
    }
    else {
      await createWaitAction(props.taskId, {
        ...waitDraft,
        preview_digest: preview.value.preview_digest,
      })
    }
    visible.value = false
    window.$message?.success($t("page.research.digitalActionCreated"))
    emit("created")
  }
  finally {
    submitting.value = false
  }
}

watch(waitPreset, applyWaitPreset, { immediate: true })
</script>

<style scoped>
.digital-preview {
  border: 1px solid rgb(226 232 240);
  border-radius: 0.875rem;
  background: rgb(248 250 252);
  padding: 1rem;
}

.digital-preview__facts {
  display: grid;
  gap: 0.625rem;
}

.digital-preview__facts > div {
  display: grid;
  grid-template-columns: minmax(7rem, auto) minmax(0, 1fr);
  gap: 0.75rem;
}

.digital-preview__facts dt {
  color: rgb(100 116 139);
  font-size: 0.75rem;
}

.digital-preview__facts dd {
  min-width: 0;
  overflow-wrap: anywhere;
  font-size: 0.8125rem;
}

:global(.research-digital-modal) {
  width: min(42rem, calc(100vw - 2rem));
}
</style>
