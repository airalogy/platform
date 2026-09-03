<template>
  <section class="compute-runners" data-testid="research-compute-runners">
    <div class="panel-heading">
      <div>
        <h3>{{ $t("page.resourceLibrary.computeRunners") }}</h3>
        <p>{{ $t("page.resourceLibrary.computeRunnersHint") }}</p>
      </div>
      <n-button type="primary" @click="openRunner()">
        {{ $t("page.resourceLibrary.addComputeRunner") }}
      </n-button>
    </div>

    <n-alert type="warning" :bordered="false" class="mb-5">
      {{ $t("page.resourceLibrary.computeRunnerSecurityHint") }}
    </n-alert>

    <n-spin :show="loading">
      <n-empty
        v-if="!runners.length && !loading"
        :description="$t('page.resourceLibrary.noComputeRunners')"
        class="py-12"
      />
      <div v-else class="runner-grid">
        <article
          v-for="runner in runners"
          :key="runner.id"
          class="runner-card"
          :class="{ 'runner-card--selected': selectedRunner?.id === runner.id }"
        >
          <button type="button" class="runner-card__main" @click="selectRunner(runner)">
            <span class="runner-card__heading">
              <strong>{{ runner.name }}</strong>
              <n-tag size="small" :type="runner.enabled ? 'success' : 'default'">
                {{ runner.enabled ? $t("page.resourceLibrary.enabled") : $t("page.resourceLibrary.disabled") }}
              </n-tag>
              <n-tag size="small" :type="runnerReady(runner) ? 'success' : 'warning'">
                {{ runnerReady(runner) ? $t("page.resourceLibrary.runnerReady") : $t("page.resourceLibrary.runnerNotReady") }}
              </n-tag>
            </span>
            <span class="aira-type-body aira-text-secondary">
              {{ runner.description || $t("page.resourceLibrary.noDescription") }}
            </span>
            <small class="aira-type-caption aira-text-muted">
              {{ $t("page.resourceLibrary.credentialHint", { hint: runner.token_hint }) }}
              ·
              {{ runner.last_seen_at ? formatDate(runner.last_seen_at) : $t("page.resourceLibrary.neverConnected") }}
              ·
              {{ $t("page.resourceLibrary.runnerConcurrency", { count: runner.max_concurrent_jobs }) }}
            </small>
          </button>
          <n-space size="small">
            <n-button size="small" secondary @click="openRunner(runner)">
              {{ $t("common.edit") }}
            </n-button>
            <n-button size="small" secondary @click="openRotation(runner)">
              {{ $t("page.resourceLibrary.rotateCredential") }}
            </n-button>
          </n-space>
        </article>
      </div>
    </n-spin>

    <section v-if="selectedRunner" class="binding-panel">
      <div class="panel-heading">
        <div>
          <h4>{{ $t("page.resourceLibrary.runnerEnvironments") }}</h4>
          <p>{{ $t("page.resourceLibrary.runnerEnvironmentsHint", { runner: selectedRunner.name }) }}</p>
        </div>
        <n-button type="primary" :disabled="!selectedRunner.enabled || !availableEnvironmentOptions.length" @click="openBinding">
          {{ $t("page.resourceLibrary.bindComputeEnvironment") }}
        </n-button>
      </div>
      <n-data-table
        :columns="bindingColumns"
        :data="bindings"
        :bordered="false"
        :single-line="false"
        :scroll-x="760"
      />
      <n-empty
        v-if="!bindings.length && !loadingBindings"
        :description="$t('page.resourceLibrary.noRunnerEnvironments')"
        class="py-10"
      />
    </section>

    <n-modal
      v-model:show="runnerModalVisible"
      preset="dialog"
      :title="editingRunner ? $t('page.resourceLibrary.editComputeRunner') : $t('page.resourceLibrary.addComputeRunner')"
      :show-icon="false"
      :mask-closable="false"
      @after-leave="resetRunnerModal"
    >
      <template v-if="!runnerPreview">
        <n-form label-placement="top">
          <n-form-item :label="$t('common.name')" required>
            <n-input v-model:value="runnerForm.name" />
          </n-form-item>
          <n-form-item :label="$t('common.description')">
            <n-input v-model:value="runnerForm.description" type="textarea" :autosize="{ minRows: 2, maxRows: 5 }" />
          </n-form-item>
          <n-form-item :label="$t('page.resourceLibrary.runnerConcurrencyLabel')" required>
            <n-input-number v-model:value="runnerForm.max_concurrent_jobs" :min="1" :max="64" class="w-full" />
          </n-form-item>
          <n-form-item :label="$t('page.resourceLibrary.enabled')">
            <n-switch v-model:value="runnerForm.enabled" />
          </n-form-item>
          <n-form-item :label="$t('page.resourceLibrary.changeReason')">
            <n-input v-model:value="runnerForm.reason" />
          </n-form-item>
        </n-form>
      </template>
      <n-alert v-else type="warning" :bordered="false">
        {{ editingRunner ? $t("page.resourceLibrary.computeRunnerUpdateImpact") : $t("page.resourceLibrary.computeRunnerCreateImpact") }}
      </n-alert>
      <template #action>
        <n-button v-if="runnerPreview" @click="runnerPreview = null">
          {{ $t("common.previous") }}
        </n-button>
        <n-button v-else @click="runnerModalVisible = false">
          {{ $t("common.cancel") }}
        </n-button>
        <n-button v-if="!runnerPreview" type="primary" :disabled="!runnerForm.name.trim()" :loading="saving" @click="previewRunner">
          {{ $t("common.preview") }}
        </n-button>
        <n-button v-else type="primary" :loading="saving" @click="confirmRunner">
          {{ $t("common.confirm") }}
        </n-button>
      </template>
    </n-modal>

    <n-modal
      v-model:show="rotationModalVisible"
      preset="dialog"
      :title="$t('page.resourceLibrary.rotateCredential')"
      :show-icon="false"
      :mask-closable="false"
      @after-leave="resetRotationModal"
    >
      <n-alert type="warning" :bordered="false" class="mb-4">
        {{ $t("page.resourceLibrary.computeRunnerRotateImpact") }}
      </n-alert>
      <n-form label-placement="top">
        <n-form-item :label="$t('page.resourceLibrary.changeReason')" required>
          <n-input v-model:value="rotationReason" :disabled="Boolean(rotationPreview)" />
        </n-form-item>
      </n-form>
      <template #action>
        <n-button v-if="rotationPreview" @click="rotationPreview = null">
          {{ $t("common.previous") }}
        </n-button>
        <n-button v-else @click="rotationModalVisible = false">
          {{ $t("common.cancel") }}
        </n-button>
        <n-button v-if="!rotationPreview" type="warning" :disabled="!rotationReason.trim()" :loading="saving" @click="previewRotation">
          {{ $t("common.preview") }}
        </n-button>
        <n-button v-else type="warning" :loading="saving" @click="confirmRotation">
          {{ $t("common.confirm") }}
        </n-button>
      </template>
    </n-modal>

    <n-modal
      v-model:show="credentialModalVisible"
      preset="dialog"
      :title="$t('page.resourceLibrary.computeRunnerCredential')"
      :show-icon="false"
      :mask-closable="false"
      :close-on-esc="false"
    >
      <n-alert type="warning" class="mb-4">
        {{ $t("page.resourceLibrary.gatewayCredentialOnce") }}
      </n-alert>
      <n-input :value="issuedCredential" readonly type="textarea" :rows="3" />
      <template #action>
        <n-button secondary @click="copyCredential">
          {{ $t("page.resourceLibrary.copyCredential") }}
        </n-button>
        <n-button type="primary" @click="closeCredential">
          {{ $t("common.close") }}
        </n-button>
      </template>
    </n-modal>

    <n-modal
      v-model:show="bindingModalVisible"
      preset="dialog"
      :title="$t('page.resourceLibrary.bindComputeEnvironment')"
      :show-icon="false"
      :mask-closable="false"
      @after-leave="resetBindingModal"
    >
      <template v-if="!bindingPreview">
        <n-form label-placement="top">
          <n-form-item :label="$t('page.resourceLibrary.computeEnvironmentRevision')" required>
            <n-select
              v-model:value="bindingEnvironmentRevisionId"
              filterable
              :options="availableEnvironmentOptions"
            />
          </n-form-item>
          <n-form-item :label="$t('page.resourceLibrary.changeReason')">
            <n-input v-model:value="bindingReason" />
          </n-form-item>
        </n-form>
      </template>
      <n-alert v-else type="warning" :bordered="false">
        {{ $t("page.resourceLibrary.computeRunnerBindingImpact") }}
      </n-alert>
      <template #action>
        <n-button v-if="bindingPreview" @click="bindingPreview = null">
          {{ $t("common.previous") }}
        </n-button>
        <n-button v-else @click="bindingModalVisible = false">
          {{ $t("common.cancel") }}
        </n-button>
        <n-button v-if="!bindingPreview" type="primary" :disabled="!bindingEnvironmentRevisionId" :loading="saving" @click="previewBinding">
          {{ $t("common.preview") }}
        </n-button>
        <n-button v-else type="primary" :loading="saving" @click="confirmBinding">
          {{ $t("common.confirm") }}
        </n-button>
      </template>
    </n-modal>

    <n-modal
      v-model:show="archiveModalVisible"
      preset="dialog"
      :title="$t('page.resourceLibrary.removeRunnerEnvironment')"
      :show-icon="false"
      :mask-closable="false"
      @after-leave="resetArchiveModal"
    >
      <n-alert type="warning" :bordered="false" class="mb-4">
        {{ $t("page.resourceLibrary.removeRunnerEnvironmentImpact") }}
      </n-alert>
      <n-form label-placement="top">
        <n-form-item :label="$t('page.resourceLibrary.changeReason')" required>
          <n-input v-model:value="archiveReason" :disabled="Boolean(archivePreview)" />
        </n-form-item>
      </n-form>
      <template #action>
        <n-button v-if="archivePreview" @click="archivePreview = null">
          {{ $t("common.previous") }}
        </n-button>
        <n-button v-else @click="archiveModalVisible = false">
          {{ $t("common.cancel") }}
        </n-button>
        <n-button v-if="!archivePreview" type="warning" :disabled="!archiveReason.trim()" :loading="saving" @click="previewArchive">
          {{ $t("common.preview") }}
        </n-button>
        <n-button v-else type="warning" :loading="saving" @click="confirmArchive">
          {{ $t("common.confirm") }}
        </n-button>
      </template>
    </n-modal>
  </section>
</template>

<script setup lang="tsx">
import type { ResearchComputeEnvironment } from "@/service/api/research-compute"
import type {
  ComputeRunnerDraft,
  ComputeRunnerPreview,
  ResearchComputeRunner,
  ResearchComputeRunnerBinding,
} from "@/service/api/research-compute-runners"
import type { DataTableColumns } from "naive-ui"
import { fetchResearchComputeEnvironmentRevisions } from "@/service/api/research-compute"
import {
  archiveResearchComputeRunnerBinding,
  createResearchComputeRunner,
  createResearchComputeRunnerBinding,
  fetchResearchComputeRunnerBindings,
  fetchResearchComputeRunners,
  previewResearchComputeRunner,
  previewResearchComputeRunnerBinding,
  previewResearchComputeRunnerBindingArchive,
  previewResearchComputeRunnerRotation,
  previewResearchComputeRunnerUpdate,
  rotateResearchComputeRunnerCredential,
  updateResearchComputeRunner,
} from "@/service/api/research-compute-runners"
import { $t } from "@airalogy/shared/locales"
import { NButton } from "naive-ui"

const props = defineProps<{ labId: string }>()

interface RunnerForm {
  name: string
  description: string
  max_concurrent_jobs: number
  enabled: boolean
  reason: string
}

function emptyRunnerForm(): RunnerForm {
  return {
    name: "",
    description: "",
    max_concurrent_jobs: 1,
    enabled: true,
    reason: "",
  }
}

const loading = ref(false)
const loadingBindings = ref(false)
const saving = ref(false)
const runners = ref<ResearchComputeRunner[]>([])
const environmentRevisions = ref<ResearchComputeEnvironment[]>([])
const selectedRunner = ref<ResearchComputeRunner | null>(null)
const bindings = ref<ResearchComputeRunnerBinding[]>([])

const runnerModalVisible = ref(false)
const editingRunner = ref<ResearchComputeRunner | null>(null)
const runnerPreview = ref<ComputeRunnerPreview | null>(null)
const runnerForm = reactive<RunnerForm>(emptyRunnerForm())

const rotationModalVisible = ref(false)
const rotationRunner = ref<ResearchComputeRunner | null>(null)
const rotationReason = ref("")
const rotationPreview = ref<ComputeRunnerPreview | null>(null)

const credentialModalVisible = ref(false)
const issuedCredential = ref("")

const bindingModalVisible = ref(false)
const bindingEnvironmentRevisionId = ref<string | null>(null)
const bindingReason = ref("")
const bindingPreview = ref<ComputeRunnerPreview | null>(null)

const archiveModalVisible = ref(false)
const archiveBinding = ref<ResearchComputeRunnerBinding | null>(null)
const archiveReason = ref("")
const archivePreview = ref<ComputeRunnerPreview | null>(null)

const boundRevisionIds = computed(() => new Set(bindings.value.map(item => item.compute_environment_revision_id)))
const availableEnvironmentOptions = computed(() => environmentRevisions.value
  .filter(item => item.available && !boundRevisionIds.value.has(item.source_revision_id))
  .map(item => ({
    label: `${item.name} · ${item.metadata.environment_key} · r${item.metadata.environment_revision}`,
    value: item.source_revision_id,
  })))

const bindingColumns: DataTableColumns<ResearchComputeRunnerBinding> = [
  {
    title: () => $t("common.name"),
    key: "environment",
    minWidth: 220,
    render: row => (
      <div>
        <strong>{row.environment.name}</strong>
        <div class="aira-type-caption aira-text-muted">
          {`${row.environment.metadata.environment_key} · r${row.environment.metadata.environment_revision}`}
        </div>
      </div>
    ),
  },
  {
    title: () => $t("page.resourceLibrary.computeImage"),
    key: "image",
    minWidth: 330,
    render: row => <code class="runner-image">{row.environment.metadata.image_ref}</code>,
  },
  {
    title: () => $t("common.action"),
    key: "actions",
    width: 120,
    render: row => (
      <NButton size="small" secondary type="warning" onClick={() => openArchive(row)}>
        {$t("common.remove")}
      </NButton>
    ),
  },
]

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value))
}

function runnerReady(runner: ResearchComputeRunner) {
  const security = runner.last_report.security
  return Boolean(
    runner.enabled
    && Boolean(runner.last_seen_at)
    && Date.now() - new Date(runner.last_seen_at || 0).getTime() < 180_000
    && runner.last_report.protocol_version === runner.runner_protocol_version
    && security?.non_root
    && security.read_only_root_filesystem
    && security.network_isolation
    && security.no_host_mounts,
  )
}

function runnerPayload(): ComputeRunnerDraft {
  return {
    lab_id: props.labId,
    name: runnerForm.name.trim(),
    description: runnerForm.description.trim(),
    runner_protocol_version: "airalogy.compute-runner.v1",
    max_concurrent_jobs: runnerForm.max_concurrent_jobs,
    enabled: runnerForm.enabled,
    reason: runnerForm.reason.trim(),
  }
}

async function loadRunners() {
  if (!props.labId)
    return
  loading.value = true
  try {
    const [runnerResponse, environmentResponse] = await Promise.all([
      fetchResearchComputeRunners(props.labId),
      fetchResearchComputeEnvironmentRevisions(props.labId),
    ])
    runners.value = runnerResponse.items
    environmentRevisions.value = environmentResponse.items
    if (selectedRunner.value) {
      selectedRunner.value = runners.value.find(item => item.id === selectedRunner.value?.id) || null
      if (selectedRunner.value)
        await loadBindings()
    }
  }
  finally {
    loading.value = false
  }
}

async function loadBindings() {
  if (!selectedRunner.value) {
    bindings.value = []
    return
  }
  loadingBindings.value = true
  try {
    bindings.value = (await fetchResearchComputeRunnerBindings(selectedRunner.value.id)).items
  }
  finally {
    loadingBindings.value = false
  }
}

async function selectRunner(runner: ResearchComputeRunner) {
  selectedRunner.value = runner
  await loadBindings()
}

function openRunner(runner?: ResearchComputeRunner) {
  editingRunner.value = runner || null
  Object.assign(runnerForm, emptyRunnerForm())
  if (runner) {
    Object.assign(runnerForm, {
      name: runner.name,
      description: runner.description,
      max_concurrent_jobs: runner.max_concurrent_jobs,
      enabled: runner.enabled,
      reason: "",
    })
  }
  runnerModalVisible.value = true
}

async function previewRunner() {
  saving.value = true
  try {
    const payload = runnerPayload()
    runnerPreview.value = editingRunner.value
      ? await previewResearchComputeRunnerUpdate(editingRunner.value.id, {
        expected_revision: editingRunner.value.revision,
        name: payload.name,
        description: payload.description,
        runner_protocol_version: payload.runner_protocol_version,
        max_concurrent_jobs: payload.max_concurrent_jobs,
        enabled: payload.enabled,
        reason: payload.reason,
      })
      : await previewResearchComputeRunner(payload)
  }
  finally {
    saving.value = false
  }
}

async function confirmRunner() {
  if (!runnerPreview.value)
    return
  saving.value = true
  try {
    const payload = runnerPayload()
    if (editingRunner.value) {
      await updateResearchComputeRunner(editingRunner.value.id, {
        expected_revision: editingRunner.value.revision,
        name: payload.name,
        description: payload.description,
        runner_protocol_version: payload.runner_protocol_version,
        max_concurrent_jobs: payload.max_concurrent_jobs,
        enabled: payload.enabled,
        reason: payload.reason,
        preview_digest: runnerPreview.value.preview_digest,
      })
      window.$message?.success($t("page.resourceLibrary.computeRunnerSaved"))
    }
    else {
      const result = await createResearchComputeRunner({
        ...payload,
        preview_digest: runnerPreview.value.preview_digest,
      })
      issuedCredential.value = result.credential
      credentialModalVisible.value = true
    }
    runnerModalVisible.value = false
    await loadRunners()
  }
  finally {
    saving.value = false
  }
}

function resetRunnerModal() {
  runnerPreview.value = null
  editingRunner.value = null
  Object.assign(runnerForm, emptyRunnerForm())
}

function openRotation(runner: ResearchComputeRunner) {
  rotationRunner.value = runner
  rotationModalVisible.value = true
}

async function previewRotation() {
  if (!rotationRunner.value)
    return
  saving.value = true
  try {
    rotationPreview.value = await previewResearchComputeRunnerRotation(rotationRunner.value.id, {
      expected_revision: rotationRunner.value.revision,
      reason: rotationReason.value.trim(),
    })
  }
  finally {
    saving.value = false
  }
}

async function confirmRotation() {
  if (!rotationRunner.value || !rotationPreview.value)
    return
  saving.value = true
  try {
    const result = await rotateResearchComputeRunnerCredential(rotationRunner.value.id, {
      expected_revision: rotationRunner.value.revision,
      reason: rotationReason.value.trim(),
      preview_digest: rotationPreview.value.preview_digest,
    })
    issuedCredential.value = result.credential
    rotationModalVisible.value = false
    credentialModalVisible.value = true
    await loadRunners()
  }
  finally {
    saving.value = false
  }
}

function resetRotationModal() {
  rotationRunner.value = null
  rotationReason.value = ""
  rotationPreview.value = null
}

async function copyCredential() {
  await navigator.clipboard.writeText(issuedCredential.value)
  window.$message?.success($t("page.resourceLibrary.credentialCopied"))
}

function closeCredential() {
  issuedCredential.value = ""
  credentialModalVisible.value = false
}

function openBinding() {
  bindingModalVisible.value = true
}

async function previewBinding() {
  if (!selectedRunner.value || !bindingEnvironmentRevisionId.value)
    return
  saving.value = true
  try {
    bindingPreview.value = await previewResearchComputeRunnerBinding({
      runner_id: selectedRunner.value.id,
      compute_environment_revision_id: bindingEnvironmentRevisionId.value,
      expected_runner_revision: selectedRunner.value.revision,
      reason: bindingReason.value.trim(),
    })
  }
  finally {
    saving.value = false
  }
}

async function confirmBinding() {
  if (!selectedRunner.value || !bindingEnvironmentRevisionId.value || !bindingPreview.value)
    return
  saving.value = true
  try {
    await createResearchComputeRunnerBinding({
      runner_id: selectedRunner.value.id,
      compute_environment_revision_id: bindingEnvironmentRevisionId.value,
      expected_runner_revision: selectedRunner.value.revision,
      reason: bindingReason.value.trim(),
      preview_digest: bindingPreview.value.preview_digest,
    })
    window.$message?.success($t("page.resourceLibrary.computeRunnerBindingSaved"))
    bindingModalVisible.value = false
    await loadRunners()
  }
  finally {
    saving.value = false
  }
}

function resetBindingModal() {
  bindingEnvironmentRevisionId.value = null
  bindingReason.value = ""
  bindingPreview.value = null
}

function openArchive(binding: ResearchComputeRunnerBinding) {
  archiveBinding.value = binding
  archiveModalVisible.value = true
}

async function previewArchive() {
  if (!selectedRunner.value || !archiveBinding.value)
    return
  saving.value = true
  try {
    archivePreview.value = await previewResearchComputeRunnerBindingArchive(archiveBinding.value.id, {
      expected_runner_revision: selectedRunner.value.revision,
      reason: archiveReason.value.trim(),
    })
  }
  finally {
    saving.value = false
  }
}

async function confirmArchive() {
  if (!selectedRunner.value || !archiveBinding.value || !archivePreview.value)
    return
  saving.value = true
  try {
    await archiveResearchComputeRunnerBinding(archiveBinding.value.id, {
      expected_runner_revision: selectedRunner.value.revision,
      reason: archiveReason.value.trim(),
      preview_digest: archivePreview.value.preview_digest,
    })
    window.$message?.success($t("page.resourceLibrary.computeRunnerBindingRemoved"))
    archiveModalVisible.value = false
    await loadRunners()
  }
  finally {
    saving.value = false
  }
}

function resetArchiveModal() {
  archiveBinding.value = null
  archiveReason.value = ""
  archivePreview.value = null
}

watch(() => props.labId, loadRunners, { immediate: true })
</script>

<style scoped>
.compute-runners {
  border-top: 1px solid rgb(226 232 240);
  padding-top: 2rem;
}

.runner-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1rem;
}

.runner-card {
  display: flex;
  flex-direction: column;
  gap: 0.875rem;
  border: 1px solid rgb(226 232 240);
  border-radius: 0.875rem;
  background: white;
  padding: 1rem;
}

.runner-card--selected {
  border-color: rgb(59 130 246);
  box-shadow: 0 0 0 1px rgb(59 130 246 / 18%);
}

.runner-card__main {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  width: 100%;
  border: 0;
  background: transparent;
  padding: 0;
  color: inherit;
  text-align: left;
  cursor: pointer;
}

.runner-card__heading {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
}

.binding-panel {
  margin-top: 1.5rem;
  border-radius: 0.875rem;
  background: rgb(248 250 252);
  padding: 1rem;
}

:deep(.runner-image) {
  display: block;
  max-width: 28rem;
  overflow-wrap: anywhere;
  white-space: normal;
  font-size: 0.75rem;
}

@media (max-width: 860px) {
  .runner-grid {
    grid-template-columns: 1fr;
  }
}
</style>
