<template>
  <n-button v-if="hasEnvironments" secondary @click="open">
    <template #icon>
      <n-icon><icon-tabler-terminal-2 /></n-icon>
    </template>
    {{ $t("page.research.computeAction") }}
  </n-button>

  <n-modal
    v-model:show="visible"
    preset="card"
    class="research-compute-modal"
    :title="$t('page.research.computeAction')"
    :mask-closable="false"
    @after-leave="reset"
  >
    <n-spin :show="loading">
      <template v-if="!preview">
        <n-alert type="info" class="mb-4">
          {{ $t("page.research.computeActionHint") }}
        </n-alert>
        <n-form label-placement="top">
          <n-form-item :label="$t('page.research.computeEnvironment')" required>
            <n-select
              v-model:value="draft.compute_environment_revision_id"
              :options="environmentOptions"
              filterable
              @update:value="selectEnvironment"
            />
            <template #feedback>
              <span v-if="selectedEnvironment">
                {{ $t("page.research.computeRunnerAvailability", {
                  ready: selectedEnvironment.ready_runner_count,
                  authorized: selectedEnvironment.authorized_runner_count,
                }) }}
              </span>
            </template>
          </n-form-item>
          <n-alert
            v-if="selectedEnvironment && selectedEnvironment.ready_runner_count === 0"
            type="warning"
            class="mb-4"
          >
            {{ $t("page.research.computeNoReadyRunner") }}
          </n-alert>
          <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <n-form-item :label="$t('page.research.computeLanguage')" required>
              <n-select v-model:value="draft.language" :options="languageOptions" />
            </n-form-item>
            <n-form-item :label="$t('page.research.computeMaximumCost')">
              <n-input
                :value="maximumCost"
                disabled
              />
            </n-form-item>
          </div>
          <n-form-item :label="$t('page.research.computeSource')" required>
            <n-input
              v-model:value="draft.source_code"
              type="textarea"
              :autosize="{ minRows: 10, maxRows: 24 }"
              class="font-mono"
              :placeholder="$t('page.research.computeSourcePlaceholder')"
            />
          </n-form-item>
          <n-form-item
            :label="$t('page.research.computeInputPayload')"
            required
            :validation-status="inputPayload ? undefined : 'error'"
            :feedback="inputPayload ? $t('page.research.computeInputSchemaHint') : $t('page.research.invalidJsonObject')"
          >
            <n-input
              v-model:value="inputText"
              type="textarea"
              :autosize="{ minRows: 4, maxRows: 12 }"
              class="font-mono"
            />
          </n-form-item>
          <n-collapse v-if="selectedEnvironment" class="mb-4">
            <n-collapse-item :title="$t('page.research.pinnedContract')" name="contract">
              <pre>{{ JSON.stringify(selectedEnvironment.input_schema, null, 2) }}</pre>
            </n-collapse-item>
          </n-collapse>
          <n-form-item :label="$t('page.research.computeInputAssets')">
            <n-select
              v-model:value="selectedVersionIds"
              :options="assetVersionOptions"
              multiple
              filterable
              clearable
              :placeholder="$t('page.research.computeInputAssetsPlaceholder')"
            />
            <template #feedback>
              {{ $t("page.research.computeInputAssetsHint") }}
            </template>
          </n-form-item>
          <div v-if="selectedVersionIds.length" class="compute-input-list mb-4">
            <div v-for="versionId in selectedVersionIds" :key="versionId" class="compute-input-row">
              <span class="aira-type-meta min-w-0 flex-1 truncate">
                {{ assetVersionLabel(versionId) }}
              </span>
              <n-input
                v-model:value="mountNames[versionId]"
                size="small"
                :placeholder="$t('page.research.computeMountName')"
              />
            </div>
          </div>
          <n-form-item :label="$t('page.research.actionTitle')">
            <n-input v-model:value="draft.title" />
          </n-form-item>
          <n-form-item :label="$t('page.research.actionDescription')">
            <n-input v-model:value="draft.description" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" />
          </n-form-item>
        </n-form>
      </template>
      <template v-else>
        <n-alert type="warning">
          {{ $t("page.research.computePreviewHint") }}
        </n-alert>
        <section class="compute-preview mt-4">
          <div class="aira-type-eyebrow">{{ $t("page.research.computeEnvironment") }}</div>
          <h3 class="aira-type-card-title mb-0 mt-1">
            {{ preview.environment.name }} · r{{ preview.environment.revision }}
          </h3>
          <div class="mt-2 flex flex-wrap gap-2">
            <n-tag size="small">{{ preview.source.language }}</n-tag>
            <n-tag size="small">{{ preview.source.bytes }} B</n-tag>
            <n-tag size="small" :type="preview.ready_runner_count ? 'success' : 'warning'">
              {{ $t("page.research.computeReadyRunners", { count: preview.ready_runner_count }) }}
            </n-tag>
            <n-tag v-if="preview.command.estimated_cost" size="small" type="warning">
              ≤ {{ preview.command.estimated_cost }} {{ preview.command.currency }}
            </n-tag>
          </div>
          <div class="aira-type-meta mt-3 break-all">
            SHA-256 · {{ preview.source.sha256 }}
          </div>
          <div class="aira-type-meta mt-2 break-all">
            {{ preview.environment.image_ref }}
          </div>
        </section>
        <section class="compute-preview mt-3">
          <div class="aira-type-eyebrow">{{ $t("page.research.effects") }}</div>
          <ul class="aira-type-body aira-text-secondary mb-0 mt-2 pl-5">
            <li v-for="effect in preview.effects" :key="effect">{{ effect }}</li>
          </ul>
        </section>
      </template>
    </n-spin>
    <template #footer>
      <div class="flex justify-end gap-2">
        <n-button @click="preview ? preview = null : visible = false">
          {{ preview ? $t("page.research.backToEdit") : $t("common.cancel") }}
        </n-button>
        <n-button v-if="!preview" type="primary" :disabled="!valid" :loading="submitting" @click="handlePreview">
          {{ $t("page.research.previewAction") }}
        </n-button>
        <n-button v-else type="primary" :loading="submitting" @click="handleCreate">
          {{ $t("page.research.confirmComputeRequest") }}
        </n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import type { DataAsset } from "@/service/api/research-assets"
import type {
  ComputeActionDraft,
  ComputeActionPreview,
  ComputeOption,
} from "@/service/api/research-compute-jobs"
import { fetchResearchAssets } from "@/service/api/research-assets"
import {
  createComputeAction,
  fetchComputeOptions,
  previewComputeAction,
} from "@/service/api/research-compute-jobs"
import { $t } from "@airalogy/shared/locales"
import { nanoid } from "nanoid"

const props = defineProps<{ taskId: string, hasEnvironments: boolean }>()
const emit = defineEmits<{ created: [] }>()
const visible = ref(false)
const loading = ref(false)
const submitting = ref(false)
const options = ref<ComputeOption[]>([])
const assets = ref<DataAsset[]>([])
const inputText = ref("{}")
const selectedVersionIds = ref<string[]>([])
const mountNames = reactive<Record<string, string>>({})
const preview = ref<ComputeActionPreview | null>(null)
const previewPayload = ref<ComputeActionDraft | null>(null)
const draft = reactive({
  compute_environment_revision_id: "",
  language: "python" as "python" | "r",
  source_code: "",
  title: "",
  description: "",
})

const selectedEnvironment = computed(() => options.value.find(
  item => item.compute_environment_revision_id === draft.compute_environment_revision_id,
))
const environmentOptions = computed(() => options.value.map(item => ({
  label: `${item.name} · r${item.revision}`,
  value: item.compute_environment_revision_id,
})))
const languageOptions = computed(() => (selectedEnvironment.value?.allowed_languages || []).map(value => ({
  label: value === "python" ? "Python" : "R",
  value,
})))
const maximumCost = computed(() => selectedEnvironment.value?.estimated_cost
  ? `≤ ${selectedEnvironment.value.estimated_cost} ${selectedEnvironment.value.currency}`
  : $t("page.research.computeUnpriced"))
const inputPayload = computed(() => {
  try {
    const value = JSON.parse(inputText.value || "{}")
    return value && typeof value === "object" && !Array.isArray(value)
      ? value as Record<string, unknown>
      : null
  }
  catch {
    return null
  }
})
const assetVersionOptions = computed(() => assets.value
  .filter(asset => asset.status === "ready")
  .flatMap(asset => asset.versions
    .filter(version => Boolean(version.research_file_id))
    .map(version => ({
      label: `${asset.name} · v${version.version}`,
      value: version.id,
      asset,
      version,
    }))))
const validMountNames = computed(() => selectedVersionIds.value.every(
  id => /^[a-z0-9][\w.-]{0,127}$/i.test(mountNames[id] || ""),
))
const valid = computed(() => Boolean(
  selectedEnvironment.value
  && draft.source_code.trim()
  && inputPayload.value
  && validMountNames.value,
))

function safeMountName(value: string) {
  const normalized = value.trim().replace(/[^\w.-]+/g, "-").replace(/^[^a-z0-9]+/i, "")
  return (normalized || "input").slice(0, 128)
}

function assetVersionLabel(versionId: string) {
  return assetVersionOptions.value.find(item => item.value === versionId)?.label || versionId
}

watch(selectedVersionIds, (next) => {
  for (const versionId of next) {
    if (!mountNames[versionId]) {
      const item = assetVersionOptions.value.find(option => option.value === versionId)
      mountNames[versionId] = safeMountName(
        `${item?.asset.name || "input"}-v${item?.version.version || 1}`,
      )
    }
  }
}, { deep: true })

function selectEnvironment(value: string) {
  const selected = options.value.find(item => item.compute_environment_revision_id === value)
  if (selected && !selected.allowed_languages.includes(draft.language))
    draft.language = selected.allowed_languages[0] || "python"
}

function payload(): ComputeActionDraft {
  return {
    compute_environment_revision_id: draft.compute_environment_revision_id,
    language: draft.language,
    source_code: draft.source_code,
    input_payload: inputPayload.value || {},
    input_assets: selectedVersionIds.value.map(data_asset_version_id => ({
      data_asset_version_id,
      mount_name: mountNames[data_asset_version_id],
    })),
    title: draft.title.trim(),
    description: draft.description.trim(),
    idempotency_key: `compute-${nanoid()}`,
  }
}

async function open() {
  visible.value = true
  loading.value = true
  try {
    const [optionResult, assetResult] = await Promise.all([
      fetchComputeOptions(props.taskId),
      fetchResearchAssets(props.taskId),
    ])
    options.value = optionResult.items
    assets.value = assetResult.data_assets
    if (options.value.length === 1) {
      draft.compute_environment_revision_id = options.value[0].compute_environment_revision_id
      selectEnvironment(draft.compute_environment_revision_id)
    }
  }
  finally {
    loading.value = false
  }
}

async function handlePreview() {
  if (!valid.value)
    return
  submitting.value = true
  try {
    previewPayload.value = payload()
    preview.value = await previewComputeAction(props.taskId, previewPayload.value)
  }
  finally {
    submitting.value = false
  }
}

async function handleCreate() {
  if (!preview.value || !previewPayload.value)
    return
  submitting.value = true
  try {
    await createComputeAction(props.taskId, {
      ...previewPayload.value,
      preview_digest: preview.value.preview_digest,
    })
    window.$message?.success($t("page.research.computeRequestCreated"))
    visible.value = false
    emit("created")
  }
  finally {
    submitting.value = false
  }
}

function reset() {
  options.value = []
  assets.value = []
  preview.value = null
  previewPayload.value = null
  inputText.value = "{}"
  selectedVersionIds.value = []
  Object.keys(mountNames).forEach(key => delete mountNames[key])
  draft.compute_environment_revision_id = ""
  draft.language = "python"
  draft.source_code = ""
  draft.title = ""
  draft.description = ""
}
</script>

<style scoped>
.research-compute-modal { width: min(52rem, calc(100vw - 2rem)); }
.compute-preview,
.compute-input-list { border: 1px solid rgb(226 232 240); border-radius: 1rem; padding: 1rem; }
.compute-input-row { display: flex; align-items: center; gap: 0.75rem; }
.compute-input-row + .compute-input-row { margin-top: 0.625rem; }
.compute-input-row :deep(.n-input) { width: min(16rem, 48%); }
pre { overflow: auto; max-height: 18rem; border-radius: 0.75rem; background: rgb(248 250 252); padding: 0.75rem; font-size: 0.75rem; }
</style>
