<template>
  <section class="resource-library__panel compute-environments" data-testid="research-compute-environments">
    <div class="panel-heading">
      <div>
        <h3>{{ $t("page.resourceLibrary.computeEnvironments") }}</h3>
        <p>{{ $t("page.resourceLibrary.computeEnvironmentsHint") }}</p>
      </div>
      <n-button type="primary" @click="openEnvironment()">
        {{ $t("page.resourceLibrary.addComputeEnvironment") }}
      </n-button>
    </div>

    <n-alert type="info" class="mb-5">
      {{ $t("page.resourceLibrary.computeGovernanceHint") }}
    </n-alert>

    <n-spin :show="loading">
      <n-empty
        v-if="!environments.length && !loading"
        :description="$t('page.resourceLibrary.noComputeEnvironments')"
        class="py-12"
      />
      <div v-else class="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <article
          v-for="environment in environments"
          :key="environment.source_id"
          class="compute-card"
        >
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div class="min-w-0">
              <div class="flex flex-wrap items-center gap-2">
                <strong class="aira-type-card-title">{{ environment.name }}</strong>
                <n-tag size="small" :type="environment.available ? 'success' : 'default'">
                  {{ environment.available ? $t("page.resourceLibrary.enabled") : $t("page.resourceLibrary.disabled") }}
                </n-tag>
                <n-tag
                  size="small"
                  :type="environment.risk === 'high' ? 'error' : environment.risk === 'medium' ? 'warning' : 'info'"
                >
                  {{ $t(`page.resourceLibrary.risk.${environment.risk}` as any) }}
                </n-tag>
              </div>
              <code class="aira-type-caption aira-text-muted mt-1 block break-all">
                {{ environment.metadata.environment_key }} · r{{ environment.metadata.environment_revision }}
              </code>
            </div>
            <n-button text type="primary" @click="openEnvironment(environment)">
              {{ $t("page.resourceLibrary.reviseComputeEnvironment") }}
            </n-button>
          </div>

          <p class="aira-type-body aira-text-secondary mb-4 mt-3">
            {{ environment.description || $t("page.resourceLibrary.noDescription") }}
          </p>
          <dl class="compute-grid">
            <div>
              <dt>{{ $t("page.resourceLibrary.computeRuntime") }}</dt>
              <dd>{{ environment.metadata.runtime_version }}</dd>
            </div>
            <div>
              <dt>{{ $t("page.resourceLibrary.computeLanguages") }}</dt>
              <dd>{{ environment.metadata.allowed_languages.join(", ") }}</dd>
            </div>
            <div>
              <dt>{{ $t("page.resourceLibrary.computeResources") }}</dt>
              <dd>
                {{ environment.metadata.resource_limits.cpu_millis }}m CPU ·
                {{ environment.metadata.resource_limits.memory_mb }} MB ·
                {{ environment.metadata.resource_limits.gpu_count }} GPU
              </dd>
            </div>
            <div>
              <dt>{{ $t("page.resourceLibrary.computeNetwork") }}</dt>
              <dd>{{ networkLabel(environment) }}</dd>
            </div>
          </dl>
          <div class="compute-image mt-4">
            <span>{{ $t("page.resourceLibrary.computeImage") }}</span>
            <code>{{ environment.metadata.image_ref }}</code>
          </div>
        </article>
      </div>
    </n-spin>

    <research-compute-runners-panel :lab-id="props.labId" class="mt-8" />

    <n-modal
      v-model:show="modalVisible"
      preset="card"
      class="compute-modal"
      :title="selected ? $t('page.resourceLibrary.reviseComputeEnvironment') : $t('page.resourceLibrary.addComputeEnvironment')"
      :mask-closable="false"
      @after-leave="resetModal"
    >
      <template v-if="!preview">
        <n-form label-placement="top">
          <div class="form-grid">
            <n-form-item :label="$t('page.resourceLibrary.computeKey')" required>
              <n-input
                v-model:value="form.environment_key"
                :disabled="Boolean(selected)"
                placeholder="python.analysis"
              />
            </n-form-item>
            <n-form-item :label="$t('common.name')" required>
              <n-input v-model:value="form.name" />
            </n-form-item>
          </div>
          <n-form-item :label="$t('common.description')">
            <n-input v-model:value="form.description" type="textarea" :autosize="{ minRows: 2, maxRows: 5 }" />
          </n-form-item>
          <n-form-item :label="$t('page.resourceLibrary.computeImage')" required>
            <n-input
              v-model:value="form.image_ref"
              placeholder="registry.example.org/research/python@sha256:…"
            />
            <template #feedback>
              {{ $t("page.resourceLibrary.computeImageHint") }}
            </template>
          </n-form-item>
          <div class="form-grid">
            <n-form-item :label="$t('page.resourceLibrary.computeRuntime')" required>
              <n-input v-model:value="form.runtime_version" placeholder="python-3.13" />
            </n-form-item>
            <n-form-item :label="$t('page.resourceLibrary.computeLanguages')" required>
              <n-select
                v-model:value="form.allowed_languages"
                multiple
                :options="languageOptions"
              />
            </n-form-item>
          </div>

          <h4 class="aira-type-label mb-3 mt-1">
            {{ $t("page.resourceLibrary.computeResourceLimits") }}
          </h4>
          <div class="limit-grid">
            <n-form-item label="CPU (millicores)" required>
              <n-input-number v-model:value="form.cpu_millis" :min="100" :max="64000" class="w-full" />
            </n-form-item>
            <n-form-item label="Memory (MB)" required>
              <n-input-number v-model:value="form.memory_mb" :min="128" :max="1048576" class="w-full" />
            </n-form-item>
            <n-form-item label="GPU" required>
              <n-input-number v-model:value="form.gpu_count" :min="0" :max="8" class="w-full" />
            </n-form-item>
            <n-form-item :label="$t('page.resourceLibrary.computeTimeout')" required>
              <n-input-number v-model:value="form.timeout_seconds" :min="1" :max="86400" class="w-full" />
            </n-form-item>
            <n-form-item :label="$t('page.resourceLibrary.computeOutputLimit')" required>
              <n-input-number v-model:value="form.max_output_mb" :min="1" :max="10240" class="w-full" />
            </n-form-item>
          </div>

          <div class="form-grid">
            <n-form-item :label="$t('page.resourceLibrary.computeNetwork')" required>
              <n-select v-model:value="form.network_policy" :options="networkOptions" />
            </n-form-item>
            <n-form-item :label="$t('page.resourceLibrary.riskLevel')" required>
              <n-select v-model:value="form.risk" :options="riskOptions" />
            </n-form-item>
          </div>
          <n-form-item
            v-if="form.network_policy === 'egress_allowlist'"
            :label="$t('page.resourceLibrary.computeEgressHosts')"
            required
          >
            <n-input
              v-model:value="form.egress_hosts"
              type="textarea"
              :autosize="{ minRows: 2, maxRows: 6 }"
              placeholder="api.example.org:443"
            />
            <template #feedback>
              {{ $t("page.resourceLibrary.computeEgressHint") }}
            </template>
          </n-form-item>

          <div class="form-grid">
            <n-form-item :label="$t('page.resourceLibrary.computeInputSchema')" required>
              <n-input v-model:value="form.input_schema" type="textarea" :autosize="{ minRows: 7, maxRows: 14 }" />
            </n-form-item>
            <n-form-item :label="$t('page.resourceLibrary.computeResultSchema')" required>
              <n-input v-model:value="form.result_schema" type="textarea" :autosize="{ minRows: 7, maxRows: 14 }" />
            </n-form-item>
          </div>
          <n-form-item :label="$t('page.resourceLibrary.computeSoftwareManifest')">
            <n-input v-model:value="form.software_manifest" type="textarea" :autosize="{ minRows: 4, maxRows: 10 }" />
          </n-form-item>
          <n-alert v-if="jsonError" type="error" class="mb-4">
            {{ jsonError }}
          </n-alert>

          <div class="form-grid">
            <n-form-item :label="$t('page.resourceLibrary.computeHourlyCost')">
              <n-input v-model:value="form.estimated_cost_per_hour" inputmode="decimal" />
            </n-form-item>
            <n-form-item :label="$t('page.resourceLibrary.serviceCurrency')">
              <n-select v-model:value="form.currency" clearable filterable tag :options="currencyOptions" />
            </n-form-item>
          </div>
          <div class="form-grid">
            <n-form-item :label="$t('page.resourceLibrary.enabled')">
              <n-switch v-model:value="form.enabled" />
            </n-form-item>
            <n-form-item :label="$t('page.resourceLibrary.changeReason')">
              <n-input v-model:value="form.reason" />
            </n-form-item>
          </div>
        </n-form>
      </template>

      <template v-else>
        <n-alert type="warning" class="mb-5">
          {{ $t("page.resourceLibrary.computeEnvironmentImpact") }}
        </n-alert>
        <dl class="preview-grid">
          <div>
            <dt>{{ $t("common.name") }}</dt>
            <dd>{{ preview.command.name }}</dd>
          </div>
          <div>
            <dt>{{ $t("page.resourceLibrary.revision") }}</dt>
            <dd>r{{ preview.command.environment_revision }}</dd>
          </div>
          <div class="preview-grid__wide">
            <dt>{{ $t("page.resourceLibrary.computeImage") }}</dt>
            <dd><code>{{ preview.command.image_ref }}</code></dd>
          </div>
          <div>
            <dt>{{ $t("page.resourceLibrary.computeResources") }}</dt>
            <dd>{{ previewLimitSummary }}</dd>
          </div>
          <div>
            <dt>{{ $t("page.resourceLibrary.computeNetwork") }}</dt>
            <dd>{{ previewNetworkSummary }}</dd>
          </div>
        </dl>
      </template>

      <template #footer>
        <div class="flex flex-wrap justify-end gap-2">
          <n-button @click="preview ? (preview = null) : (modalVisible = false)">
            {{ preview ? $t("page.research.backToEdit") : $t("common.cancel") }}
          </n-button>
          <n-button
            v-if="!preview"
            type="primary"
            :disabled="!formValid"
            :loading="saving"
            @click="handlePreview"
          >
            {{ $t("page.research.previewImpact") }}
          </n-button>
          <n-button v-else type="primary" :loading="saving" @click="handleSave">
            {{ $t("common.confirm") }}
          </n-button>
        </div>
      </template>
    </n-modal>
  </section>
</template>

<script setup lang="ts">
import type {
  ComputeEnvironmentDraft,
  ResearchComputeEnvironment,
  ResearchComputePreview,
} from "@/service/api/research-compute"
import {
  createResearchComputeEnvironment,
  createResearchComputeEnvironmentRevision,
  fetchResearchComputeEnvironments,
  previewResearchComputeEnvironment,
  previewResearchComputeEnvironmentRevision,
} from "@/service/api/research-compute"
import { $t } from "@airalogy/shared/locales"

const props = defineProps<{ labId: string }>()

interface ComputeForm {
  environment_key: string
  name: string
  description: string
  image_ref: string
  runtime_version: string
  allowed_languages: Array<"python" | "r">
  cpu_millis: number
  memory_mb: number
  gpu_count: number
  timeout_seconds: number
  max_output_mb: number
  network_policy: "none" | "egress_allowlist"
  egress_hosts: string
  input_schema: string
  result_schema: string
  software_manifest: string
  estimated_cost_per_hour: string
  currency: string | null
  risk: "low" | "medium" | "high"
  enabled: boolean
  reason: string
}

const EMPTY_SCHEMA = JSON.stringify({
  type: "object",
  properties: {},
  additionalProperties: false,
}, null, 2)

function emptyForm(): ComputeForm {
  return {
    environment_key: "",
    name: "",
    description: "",
    image_ref: "",
    runtime_version: "",
    allowed_languages: ["python"],
    cpu_millis: 1000,
    memory_mb: 2048,
    gpu_count: 0,
    timeout_seconds: 3600,
    max_output_mb: 100,
    network_policy: "none",
    egress_hosts: "",
    input_schema: EMPTY_SCHEMA,
    result_schema: EMPTY_SCHEMA,
    software_manifest: "{}",
    estimated_cost_per_hour: "",
    currency: null,
    risk: "medium",
    enabled: true,
    reason: "",
  }
}

const loading = ref(false)
const saving = ref(false)
const environments = ref<ResearchComputeEnvironment[]>([])
const selected = ref<ResearchComputeEnvironment | null>(null)
const modalVisible = ref(false)
const preview = ref<ResearchComputePreview | null>(null)
const jsonError = ref("")
const form = reactive<ComputeForm>(emptyForm())

const languageOptions = [
  { label: "Python", value: "python" },
  { label: "R", value: "r" },
]
const networkOptions = computed(() => [
  { label: $t("page.resourceLibrary.computeNetworkNone"), value: "none" },
  { label: $t("page.resourceLibrary.computeNetworkAllowlist"), value: "egress_allowlist" },
])
const riskOptions = computed(() => ["low", "medium", "high"].map(value => ({
  label: $t(`page.resourceLibrary.risk.${value}` as any),
  value,
})))
const currencyOptions = ["USD", "CNY", "EUR", "GBP", "JPY"].map(value => ({ label: value, value }))

const formValid = computed(() => Boolean(
  form.environment_key.trim()
  && form.name.trim()
  && form.image_ref.trim()
  && form.runtime_version.trim()
  && form.allowed_languages.length
  && form.cpu_millis
  && form.memory_mb
  && form.timeout_seconds
  && form.max_output_mb
  && (form.network_policy === "none" || lines(form.egress_hosts).length)
  && (!form.estimated_cost_per_hour || Boolean(form.currency)),
))
const previewLimitSummary = computed(() => {
  const limits = preview.value?.command.resource_limits as Record<string, number> | undefined
  return limits
    ? `${limits.cpu_millis}m CPU · ${limits.memory_mb} MB · ${limits.gpu_count} GPU · ${limits.timeout_seconds}s`
    : "-"
})
const previewNetworkSummary = computed(() => {
  if (!preview.value)
    return "-"
  const policy = String(preview.value.command.network_policy)
  const hosts = preview.value.command.allowed_egress_hosts as string[]
  return policy === "none"
    ? $t("page.resourceLibrary.computeNetworkNone")
    : hosts.join(", ")
})

function lines(value: string) {
  return value.split("\n").map(item => item.trim()).filter(Boolean)
}

function parseObject(value: string, label: string) {
  const parsed = JSON.parse(value)
  if (!parsed || Array.isArray(parsed) || typeof parsed !== "object")
    throw new Error(`${label}: ${$t("page.resourceLibrary.invalidJson")}`)
  return parsed as Record<string, unknown>
}

function payload(): ComputeEnvironmentDraft {
  return {
    lab_id: props.labId,
    environment_key: form.environment_key.trim(),
    name: form.name.trim(),
    description: form.description.trim(),
    runner_protocol_version: "airalogy.compute-runner.v1",
    image_ref: form.image_ref.trim(),
    runtime_version: form.runtime_version.trim(),
    allowed_languages: form.allowed_languages,
    resource_limits: {
      cpu_millis: form.cpu_millis,
      memory_mb: form.memory_mb,
      gpu_count: form.gpu_count,
      timeout_seconds: form.timeout_seconds,
      max_output_bytes: form.max_output_mb * 1024 * 1024,
    },
    network_policy: form.network_policy,
    allowed_egress_hosts: form.network_policy === "none" ? [] : lines(form.egress_hosts),
    input_schema: parseObject(form.input_schema, $t("page.resourceLibrary.computeInputSchema")),
    result_schema: parseObject(form.result_schema, $t("page.resourceLibrary.computeResultSchema")),
    software_manifest: parseObject(form.software_manifest, $t("page.resourceLibrary.computeSoftwareManifest")),
    estimated_cost_per_hour: form.estimated_cost_per_hour.trim() || null,
    currency: form.estimated_cost_per_hour.trim() ? form.currency : null,
    risk: form.risk,
    enabled: form.enabled,
    reason: form.reason.trim(),
  }
}

function networkLabel(environment: ResearchComputeEnvironment) {
  return environment.metadata.network_policy === "none"
    ? $t("page.resourceLibrary.computeNetworkNone")
    : environment.metadata.allowed_egress_hosts.join(", ")
}

async function loadEnvironments() {
  if (!props.labId)
    return
  loading.value = true
  try {
    environments.value = (await fetchResearchComputeEnvironments(props.labId)).items
  }
  finally {
    loading.value = false
  }
}

function openEnvironment(environment?: ResearchComputeEnvironment) {
  selected.value = environment || null
  Object.assign(form, emptyForm())
  if (environment) {
    Object.assign(form, {
      environment_key: environment.metadata.environment_key,
      name: environment.name,
      description: environment.description,
      image_ref: environment.metadata.image_ref,
      runtime_version: environment.metadata.runtime_version,
      allowed_languages: [...environment.metadata.allowed_languages],
      cpu_millis: environment.metadata.resource_limits.cpu_millis,
      memory_mb: environment.metadata.resource_limits.memory_mb,
      gpu_count: environment.metadata.resource_limits.gpu_count,
      timeout_seconds: environment.metadata.resource_limits.timeout_seconds,
      max_output_mb: environment.metadata.resource_limits.max_output_bytes / 1024 / 1024,
      network_policy: environment.metadata.network_policy,
      egress_hosts: environment.metadata.allowed_egress_hosts.join("\n"),
      input_schema: JSON.stringify(environment.input_schema, null, 2),
      result_schema: JSON.stringify(environment.output_schema, null, 2),
      software_manifest: JSON.stringify(environment.metadata.software_manifest, null, 2),
      estimated_cost_per_hour: environment.metadata.estimated_cost_per_hour || "",
      currency: environment.metadata.currency || null,
      risk: environment.risk,
      enabled: environment.available,
      reason: "",
    })
  }
  modalVisible.value = true
}

async function handlePreview() {
  jsonError.value = ""
  saving.value = true
  try {
    const draft = payload()
    preview.value = selected.value
      ? await previewResearchComputeEnvironmentRevision(selected.value.source_id, {
        ...draft,
        expected_revision: selected.value.metadata.environment_revision,
      })
      : await previewResearchComputeEnvironment(draft)
  }
  catch (error) {
    if (error instanceof SyntaxError || (error instanceof Error && error.message.includes($t("page.resourceLibrary.invalidJson"))))
      jsonError.value = error instanceof Error ? error.message : $t("page.resourceLibrary.invalidJson")
    else
      throw error
  }
  finally {
    saving.value = false
  }
}

async function handleSave() {
  if (!preview.value)
    return
  saving.value = true
  try {
    const draft = payload()
    if (selected.value) {
      await createResearchComputeEnvironmentRevision(selected.value.source_id, {
        ...draft,
        expected_revision: selected.value.metadata.environment_revision,
        preview_digest: preview.value.preview_digest,
      })
    }
    else {
      await createResearchComputeEnvironment({
        ...draft,
        preview_digest: preview.value.preview_digest,
      })
    }
    window.$message?.success($t("page.resourceLibrary.computeEnvironmentSaved"))
    modalVisible.value = false
    await loadEnvironments()
  }
  finally {
    saving.value = false
  }
}

function resetModal() {
  preview.value = null
  selected.value = null
  jsonError.value = ""
  Object.assign(form, emptyForm())
}

watch(() => props.labId, loadEnvironments, { immediate: true })
</script>

<style scoped>
.compute-environments {
  min-height: 20rem;
}

.compute-card {
  border: 1px solid rgb(226 232 240);
  border-radius: 0.875rem;
  background: white;
  padding: 1.125rem;
}

.compute-grid,
.preview-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.875rem 1rem;
  margin: 0;
}

.compute-grid dt,
.preview-grid dt,
.compute-image span {
  color: rgb(100 116 139);
  font-size: 0.75rem;
}

.compute-grid dd,
.preview-grid dd {
  margin: 0.25rem 0 0;
  overflow-wrap: anywhere;
}

.compute-image code {
  display: block;
  margin-top: 0.25rem;
  overflow-wrap: anywhere;
  color: rgb(51 65 85);
  font-size: 0.75rem;
}

.compute-modal {
  width: min(58rem, calc(100vw - 2rem));
}

.form-grid,
.limit-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 1rem;
}

.limit-grid {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.preview-grid__wide {
  grid-column: 1 / -1;
}

@media (max-width: 640px) {
  .compute-grid,
  .preview-grid,
  .form-grid,
  .limit-grid {
    grid-template-columns: 1fr;
  }
}
</style>
