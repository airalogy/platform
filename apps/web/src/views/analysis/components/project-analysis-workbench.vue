<template>
  <div class="project-workbench py-8" data-testid="project-analysis-workbench">
    <header class="mb-5 flex flex-wrap items-start justify-between gap-3">
      <div class="min-w-0">
        <h1 class="aira-type-page-title">
          {{ t("page.projectAnalysis.title") }}
        </h1><p class="aira-type-body aira-text-secondary max-w-3xl">
          {{ t("page.projectAnalysis.description") }}
        </p>
      </div>
      <div class="flex flex-wrap gap-2">
        <n-button @click="emit('single')">
          {{ t("page.projectAnalysis.singleProtocol") }}
        </n-button><n-button :loading="loading" @click="initialize">
          {{ t("common.refresh") }}
        </n-button>
      </div>
    </header>
    <n-alert type="info" class="mb-4">
      {{ t("page.projectAnalysis.privateHint") }}
    </n-alert>
    <n-alert v-if="error" type="error" class="mb-4" data-testid="project-analysis-error">
      {{ error }}<project-join-audit v-if="errorAudit" :audit="errorAudit" :labels="slotLabels" />
    </n-alert>
    <n-spin :show="loading">
      <div class="workbench-grid">
        <section class="project-panel">
          <h2 class="aira-type-section-title mt-0">
            {{ t("page.analysis.configure") }}
          </h2>
          <n-form label-placement="top" :disabled="busy || methodLoading">
            <n-form-item :label="t('page.analysis.question')">
              <n-input
                v-model:value="question"
                type="textarea"
                :maxlength="4000"
                :autosize="{ minRows: 2, maxRows: 5 }"
                data-testid="project-analysis-question"
              />
            </n-form-item>
            <n-form-item :label="t('page.projectAnalysis.mode')">
              <n-select
                :value="recipe.mode"
                :options="modeOptions"
                data-testid="project-analysis-mode"
                @update:value="changeMode"
              />
            </n-form-item>
            <n-alert type="info" class="mb-4">
              {{
                t(
                  recipe.mode === "relational"
                    ? "page.projectAnalysis.joinHint"
                    : "page.projectAnalysis.separateEvidence",
                )
              }}
            </n-alert>
            <article
              v-for="(slot, index) in recipe.slots"
              :key="slot.slot_id"
              class="source-card mb-4"
              :data-slot-id="slot.slot_id"
              data-testid="project-analysis-slot"
            >
              <div class="mb-3 flex flex-wrap items-center justify-between gap-2">
                <h3 class="aira-type-section-title my-0">
                  {{ t("page.projectAnalysis.sourceNumber", { number: index + 1 }) }}
                </h3><n-button
                  size="small"
                  :disabled="recipe.slots.length <= 2 || recipe.mode === 'relational'"
                  @click="removeSlot(index)"
                >
                  {{ t("common.delete") }}
                </n-button>
              </div>
              <n-form-item :label="t('page.projectAnalysis.sourceLabel')" required>
                <n-input
                  v-model:value="slot.label"
                  :maxlength="255"
                  data-testid="project-source-label"
                />
              </n-form-item>
              <project-analysis-source
                v-model="selection.inputs[index]"
                :project-id="projectId"
                :protocols="protocols"
                :used-protocol-ids="selection.inputs.map(input => input.protocol_id)"
                @fields="value => (fields[slot.slot_id] = value)"
                @changed-protocol="slot.recipe = emptyProjectStatistics()"
                @validity="valid => (sourceValidity[slot.slot_id] = valid)"
              >
                <project-statistics-editor
                  v-model="slot.recipe"
                  :fields="fields[slot.slot_id] || []"
                  @validity="valid => (recipeValidity[slot.slot_id] = valid)"
                />
              </project-analysis-source>
            </article>
            <n-button
              v-if="recipe.mode === 'evidence_synthesis'"
              class="mb-4"
              :disabled="recipe.slots.length >= 8"
              data-testid="project-add-source"
              @click="addSlot"
            >
              {{ t("page.projectAnalysis.addSource") }}
            </n-button>
            <project-join-editor
              v-if="recipe.join"
              v-model="recipe.join"
              :slots="recipe.slots"
              :fields="fields"
              @validity="valid => (recipeValidity.join = valid)"
            />
            <n-alert v-if="validation" type="warning" class="my-4">
              {{ t(`page.projectAnalysis.validation.${validation}`) }}
            </n-alert>
            <n-alert v-if="methodChanged" type="info" class="my-4">
              {{ t("page.analysis.methodChanged") }}
            </n-alert>
            <div class="mt-4 flex flex-wrap gap-2">
              <n-button
                type="primary"
                :disabled="!valid || methodChanged"
                :loading="busy || methodLoading"
                data-testid="project-analysis-preview"
                @click="previewAnalysis"
              >
                {{ t("page.analysis.preview") }}
              </n-button>
              <n-button
                v-if="method"
                :disabled="!valid"
                data-testid="project-save-revision"
                @click="confirmRevision"
              >
                {{ t("page.analysis.saveRevision", { number: method.current_revision + 1 }) }}
              </n-button>
            </div>
          </n-form>
        </section>
        <div class="min-w-0 space-y-5">
          <section v-if="run" class="project-panel" data-testid="project-analysis-report">
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div class="min-w-0">
                <h2 class="aira-type-section-title mt-0">
                  {{ run.question || t("page.analysis.report") }}
                </h2><p class="aira-type-meta">
                  {{ formatTime(run.created_at) }} · {{ t(`page.analysis.status.${run.status}`) }}
                </p>
              </div>
              <div class="flex flex-wrap gap-2">
                <n-button
                  v-if="['pending', 'running'].includes(run.status)"
                  size="small"
                  @click="confirmCancel"
                >
                  {{ t("common.cancel") }}
                </n-button>
                <n-button
                  v-if="run.status === 'succeeded'"
                  size="small"
                  data-testid="project-save-method"
                  @click="saveVisible = true"
                >
                  {{ t("page.analysis.saveMethod") }}
                </n-button>
                <n-button size="small" :disabled="busy" data-testid="project-analysis-rerun" @click="prepareRerun">
                  {{ t("page.analysis.rerun") }}
                </n-button>
                <n-button
                  v-if="run.result"
                  size="small"
                  data-testid="project-download-report"
                  @click="download"
                >
                  {{ t("page.analysis.download") }}
                </n-button>
              </div>
            </div>
            <n-alert v-if="run.error" type="error" class="my-3">
              {{ run.error }}
            </n-alert>
            <n-alert v-if="['pending', 'running'].includes(run.status)" type="info" class="my-3">
              {{ t("page.analysis.runningHint") }}
            </n-alert>
            <project-analysis-result v-if="run.result" :result="run.result" @source="openSource" />
            <details
              v-if="run.source_snapshot"
              class="aira-disclosure mt-4"
              data-testid="project-source-provenance"
            >
              <summary>{{ t("page.analysis.provenance") }}</summary>
              <section v-for="input in run.source_snapshot.inputs" :key="input.slot_id">
                <h4 class="aira-type-label">
                  {{
                    run.recipe.slots.find(slot => slot.slot_id === input.slot_id)?.label
                      || input.slot_id
                  }}
                </h4>
                <p
                  v-for="source in input.snapshot.records"
                  :key="`${source.record_id}:${source.record_version}`"
                  class="aira-type-meta break-anywhere"
                >
                  <n-button
                    text
                    class="source-link"
                    @click="openSource({ ...source, protocol_id: input.snapshot.protocol_id })"
                  >
                    #{{ source.number }} · Record {{ source.record_id }} · v{{
                      source.record_version
                    }}
                    · Protocol {{ source.protocol_version }}
                  </n-button>
                </p>
              </section>
            </details>
            <project-analysis-interpretation
              v-if="run.status === 'succeeded' && run.result"
              :run="run"
            />
            <project-analysis-comparison
              v-if="run.status === 'succeeded'"
              :run="run"
              :candidates="runs"
            />
            <analysis-publication-panel v-if="run.status === 'succeeded'" :key="run.id" :analysis-id="run.id" />
          </section>
          <section class="project-panel">
            <h2 class="aira-type-section-title mt-0">
              {{ t("page.analysis.history") }}
            </h2><n-empty v-if="!runs.length" :description="t('page.analysis.noRuns')" /><button
              v-for="item in runs"
              :key="item.id"
              class="history-item"
              data-testid="project-analysis-history-item"
              @click="openRun(item.id)"
            >
              <span>{{ item.question || t("page.analysis.report") }}</span><span class="aira-type-meta">{{ formatTime(item.created_at) }} ·
                {{ t(`page.analysis.status.${item.status}`) }}</span>
            </button>
          </section>
          <section class="project-panel">
            <h2 class="aira-type-section-title mt-0">
              {{ t("page.analysis.savedMethods") }}
            </h2><n-empty v-if="!methods.length" :description="t('page.analysis.noMethods')" />
            <div v-for="item in methods" :key="item.id" class="mb-3">
              <button class="history-item" data-testid="project-analysis-method" @click="loadMethod(item.id)">
                <span>{{ item.title }}</span><span class="aira-type-meta">r{{ item.current_revision }} · {{ t("page.analysis.loadMethod") }}</span>
              </button>
              <n-button class="mt-2" size="small" :disabled="busy || methodLoading" data-testid="project-analysis-publish-method" @click="openMethodPublication(item.id)">
                {{ t('page.workflowAnalysis.publishTitle') }}
              </n-button>
            </div>
          </section>
        </div>
      </div>
    </n-spin>
    <analysis-method-publish-modal v-model:show="publishMethodVisible" :project-id="projectId" :project-name="projectName" :pipeline-id="publishPipelineId" />
    <n-modal
      v-model:show="previewVisible"
      preset="card"
      class="aira-dialog"
      style="--aira-dialog-width: 60rem"
      :title="t('page.analysis.confirmTitle')"
      :mask-closable="false"
      :closable="!busy"
      data-testid="project-analysis-preview-dialog"
    >
      <template v-if="preview">
        <n-alert type="info">
          {{ t("page.projectAnalysis.destination", { project: preview.summary.project_name }) }}
        </n-alert>
        <p class="aira-type-body">
          {{ preview.question }}
        </p>
        <n-alert v-if="error" type="error" class="my-3">
          {{ error }}
        </n-alert>
        <project-analysis-result :result="preview.summary" @source="openSource" />
        <details class="aira-disclosure mt-4">
          <summary>{{ t("page.analysis.provenance") }}</summary><div v-for="input in preview.summary.source_inputs" :key="input.slot_id">
            <h4>{{ preview.recipe.slots.find(slot => slot.slot_id === input.slot_id)?.label }}</h4><p
              v-for="source in input.sources"
              :key="`${source.record_id}:${source.record_version}`"
              class="aira-type-meta break-anywhere"
            >
              #{{ source.number }} · Record {{ source.record_id }} · v{{ source.record_version }} ·
              Protocol {{ source.protocol_version }}
            </p>
          </div>
        </details>
        <p class="aira-type-meta break-anywhere">
          {{ t("page.analysis.recipeDigest") }}: {{ preview.recipe_digest }}
        </p>
        <p class="aira-type-meta">
          {{ t("page.analysis.expiresAt", { time: formatTime(preview.expires_at) }) }}
        </p>
        <n-checkbox v-model:checked="previewReviewed" data-testid="project-preview-reviewed">
          {{ t("page.projectAnalysis.previewReviewed") }}
        </n-checkbox>
      </template>
      <template #footer>
        <div class="flex flex-wrap justify-end gap-2">
          <n-button :disabled="busy" @click="previewVisible = false">
            {{ t("page.analysis.backToEdit") }}
          </n-button><n-button
            type="primary"
            :loading="busy"
            :disabled="!previewReviewed"
            data-testid="project-analysis-confirm"
            @click="confirmAnalysis"
          >
            {{ t("page.analysis.confirm") }}
          </n-button>
        </div>
      </template>
    </n-modal>
    <n-modal
      v-model:show="saveVisible"
      preset="card"
      class="aira-dialog"
      style="--aira-dialog-width: 32rem"
      :title="t('page.analysis.saveMethod')"
      :mask-closable="false"
    >
      <n-alert type="info" class="mb-4">
        {{ t("page.analysis.saveMethodHint") }}
      </n-alert><n-input
        v-model:value="methodTitle"
        :maxlength="255"
        :placeholder="t('page.analysis.methodTitle')"
        data-testid="project-method-title"
      />
      <template #footer>
        <n-button
          type="primary"
          :disabled="!methodTitle.trim()"
          :loading="busy"
          data-testid="project-confirm-save-method"
          @click="saveMethod"
        >
          {{ t("common.save") }}
        </n-button>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import type { AnalysisField } from "@/service/api/analysis"
import type {
  ProjectAnalysisJoinAudit,
  ProjectAnalysisPipeline,
  ProjectAnalysisPreview,
  ProjectAnalysisProtocol,
  ProjectAnalysisRecipe,
  ProjectAnalysisRecordRef,
  ProjectAnalysisRun,
  ProjectAnalysisSelection,
} from "@/service/api/project-analysis"
import { cancelAnalysis } from "@/service/api/analysis"
import {
  createProjectAnalysis,
  downloadProjectAnalysis,
  fetchProjectAnalysisContext,
  fetchProjectAnalysisMethod,
  fetchProjectAnalysisMethods,
  fetchProjectAnalysisRun,
  fetchProjectAnalysisRuns,
  previewProjectAnalysis,
  reviseProjectAnalysisMethod,
  saveProjectAnalysisMethod,
} from "@/service/api/project-analysis"
import { getProtocolInfo } from "@/service/api/project-protocols"
import {
  createProjectEditorLoader,
  emptyProjectStatistics,
  newProjectAnalysisSlot,
  projectAnalysisIdentity,
  projectAnalysisValidation,
} from "@/utils/project-analysis"
import { downloadAs } from "@airalogy/shared/utils"
import { useDialog, useMessage } from "naive-ui"
import { useI18n } from "vue-i18n"
import AnalysisMethodPublishModal from "./analysis-method-publish-modal.vue"
import AnalysisPublicationPanel from "./analysis-publication-panel.vue"
import ProjectAnalysisComparison from "./project-analysis-comparison.vue"
import ProjectAnalysisInterpretation from "./project-analysis-interpretation.vue"
import ProjectAnalysisResult from "./project-analysis-result.vue"
import ProjectAnalysisSource from "./project-analysis-source.vue"
import ProjectJoinAudit from "./project-join-audit.vue"
import ProjectJoinEditor from "./project-join-editor.vue"
import ProjectStatisticsEditor from "./project-statistics-editor.vue"

const props = defineProps<{ projectId: string }>()
const emit = defineEmits<{ single: [] }>()
const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()
const dialog = useDialog()
const message = useMessage()
const projectName = ref("")
const publishMethodVisible = ref(false)
const publishPipelineId = ref<string>()
function openMethodPublication(id: string) {
  publishPipelineId.value = id
  publishMethodVisible.value = true
}
const protocols = ref<ProjectAnalysisProtocol[]>([])
const recipe = ref<ProjectAnalysisRecipe>({
  kind: "project",
  schema_version: 1,
  mode: "evidence_synthesis",
  slots: [],
  join: null,
})
const selection = ref<ProjectAnalysisSelection>({
  schema: "airalogy.project-selection.v1",
  inputs: [],
})
const fields = ref<Record<string, AnalysisField[]>>({})
const sourceValidity = ref<Record<string, boolean>>({})
const recipeValidity = ref<Record<string, boolean>>({})
const question = ref("")
const error = ref("")
const errorAudit = ref<ProjectAnalysisJoinAudit | null>(null)
const busy = ref(false)
const loading = ref(false)
const methodLoading = ref(false)
const editorLoader = createProjectEditorLoader(value => (methodLoading.value = value))
const runs = ref<ProjectAnalysisRun[]>([])
const methods = ref<ProjectAnalysisPipeline[]>([])
const run = ref<ProjectAnalysisRun | null>(null)
const method = ref<ProjectAnalysisPipeline | null>(null)
const pipelineRevisionId = ref<string>()
const rerunOfId = ref<string>()
const preview = ref<ProjectAnalysisPreview | null>(null)
const previewVisible = ref(false)
const previewReviewed = ref(false)
const saveVisible = ref(false)
const methodTitle = ref("")
let confirmationKey = ""
let sequence = 0
let runSequence = 0
let poll: ReturnType<typeof setTimeout> | undefined
function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}
const modeOptions = computed(() =>
  (["evidence_synthesis", "relational"] as const).map(value => ({
    value,
    label: t(`page.projectAnalysis.modes.${value}`),
    disabled: value === "relational" && recipe.value.slots.length > 2,
  })),
)
const slotLabels = computed(() =>
  Object.fromEntries(recipe.value.slots.map(slot => [slot.slot_id, slot.label])),
)
const validation = computed(() =>
  projectAnalysisValidation(recipe.value, selection.value, fields.value),
)
const valid = computed(
  () =>
    !methodLoading.value
    && !validation.value
    && recipe.value.slots.every(
      slot => sourceValidity.value[slot.slot_id] && recipeValidity.value[slot.slot_id] !== false,
    )
    && recipeValidity.value.join !== false,
)
const methodChanged = computed(() =>
  Boolean(
    method.value
    && projectAnalysisIdentity(recipe.value)
    !== projectAnalysisIdentity(method.value.current_recipe),
  ),
)
function formatTime(value: string) {
  return new Date(value).toLocaleString(locale.value)
}
function showError(cause: unknown) {
  const detail = (cause as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  const object
    = detail && typeof detail === "object"
      ? (detail as { message?: string, audit?: ProjectAnalysisJoinAudit })
      : null
  error.value
    = typeof detail === "string" ? detail : object?.message || t("page.analysis.requestError")
  errorAudit.value = object?.audit || null
}
function addSlot() {
  const slot = newProjectAnalysisSlot(
    recipe.value.slots,
    t("page.projectAnalysis.sourceNumber", { number: recipe.value.slots.length + 1 }),
  )
  recipe.value.slots.push(slot)
  selection.value.inputs.push({
    slot_id: slot.slot_id,
    protocol_id: "",
    selection: { mode: "latest", filters: {} },
  })
}
function removeSlot(index: number) {
  const [slot] = recipe.value.slots.splice(index, 1)
  selection.value.inputs = selection.value.inputs.filter(input => input.slot_id !== slot.slot_id)
  delete fields.value[slot.slot_id]
}
function changeMode(mode: ProjectAnalysisRecipe["mode"]) {
  recipe.value.mode = mode
  recipe.value.join
    = mode === "relational"
      ? {
          left_slot_id: recipe.value.slots[0].slot_id,
          right_slot_id: recipe.value.slots[1].slot_id,
          kind: "inner",
          cardinality: "one_to_one",
          keys: [{ left_field: "", right_field: "" }],
          missing_key_policy: "error",
          duplicate_key_policy: "error",
          semantic_alignment_confirmed: false,
          outputs: [],
          recipe: emptyProjectStatistics(),
        }
      : null
  recipeValidity.value.join = true
}
async function refreshLists() {
  const id = props.projectId
  const [history, saved] = await Promise.all([
    fetchProjectAnalysisRuns(id),
    fetchProjectAnalysisMethods(id),
  ])
  if (id !== props.projectId)
    return
  runs.value = history.items.filter(item => item.source_scope === "project")
  methods.value = saved.items.filter(item => item.source_scope === "project")
}
async function initialize() {
  editorLoader.cancel()
  const current = ++sequence
  loading.value = true
  error.value = ""
  try {
    const entries: ProjectAnalysisProtocol[] = []
    let offset: number | null = 0
    while (offset !== null) {
      const context = await fetchProjectAnalysisContext(props.projectId, offset)
      if (current !== sequence)
        return
      projectName.value = context.project_name
      entries.push(...context.protocols)
      offset = context.next_offset
    }
    protocols.value = entries
    if (!recipe.value.slots.length) {
      addSlot()
      addSlot()
    }
    await refreshLists()
    if (typeof route.query.runId === "string")
      await openRun(route.query.runId, false)
  }
  catch (cause) {
    if (current === sequence)
      showError(cause)
  }
  finally {
    if (current === sequence)
      loading.value = false
  }
}
async function previewAnalysis() {
  if (!valid.value || busy.value)
    return
  busy.value = true
  error.value = ""
  errorAudit.value = null
  try {
    preview.value = await previewProjectAnalysis({
      project_id: props.projectId,
      question: question.value,
      recipe: clone(recipe.value),
      selection: clone(selection.value),
      pipeline_revision_id: pipelineRevisionId.value,
      rerun_of_id: rerunOfId.value,
    })
    confirmationKey = `project-analysis-${Array.from(crypto.getRandomValues(new Uint8Array(16)), value => value.toString(16).padStart(2, "0")).join("")}`
    previewReviewed.value = false
    previewVisible.value = true
  }
  catch (cause) {
    showError(cause)
  }
  finally {
    busy.value = false
  }
}
async function confirmAnalysis() {
  if (!preview.value || !previewReviewed.value || busy.value)
    return
  busy.value = true
  try {
    const result = await createProjectAnalysis({
      preview_id: preview.value.id,
      preview_digest: preview.value.preview_digest,
      client_idempotency_key: confirmationKey,
    })
    previewVisible.value = false
    await openRun(result.id)
    await refreshLists()
  }
  catch (cause) {
    showError(cause)
    if ((cause as { response?: { status?: number } })?.response?.status === 409) {
      preview.value = null
      previewVisible.value = false
    }
  }
  finally {
    busy.value = false
  }
}
async function openRun(id: string, updateRoute = true) {
  const current = ++runSequence
  if (poll)
    clearTimeout(poll)
  try {
    const result = await fetchProjectAnalysisRun(id)
    if (current !== runSequence)
      return
    if (result.source_scope !== "project" || result.project_id !== props.projectId)
      throw new Error("Unexpected analysis scope")
    const statusChanged = run.value?.id === result.id && run.value.status !== result.status
    run.value = result
    if (statusChanged)
      await refreshLists()
    if (updateRoute)
      await router.replace({ name: "project-analysis", params: { labUid: route.params.labUid, projectUid: route.params.projectUid }, query: { scope: "project", runId: id } })
    if (["pending", "running"].includes(result.status))
      poll = setTimeout(() => void openRun(id, false), 1500)
  }
  catch (cause) {
    if (current === runSequence) {
      run.value = null
      showError(cause)
    }
  }
}
function applyMethod(value: ProjectAnalysisRecipe, scope: ProjectAnalysisSelection) {
  sourceValidity.value = {}
  recipeValidity.value = {}
  fields.value = {}
  recipe.value = clone(value)
  // Stored inputs are canonically sorted by ID; editor order follows recipe slots.
  selection.value = {
    schema: scope.schema,
    inputs: value.slots.map(slot =>
      clone(scope.inputs.find(input => input.slot_id === slot.slot_id)!),
    ),
  }
}
async function loadMethod(id: string) {
  if (busy.value)
    return
  const projectId = props.projectId
  try {
    await editorLoader.load(() => fetchProjectAnalysisMethod(id), (saved) => {
      if (saved.source_scope !== "project" || saved.project_id !== projectId || projectId !== props.projectId)
        throw new Error("Unexpected method scope")
      const revision = saved.revisions?.find(revision => revision.revision === saved.current_revision)
      if (!revision)
        throw new Error("Method revision unavailable")
      applyMethod(saved.current_recipe, revision.source_selection)
      method.value = saved
      pipelineRevisionId.value = revision.id
      rerunOfId.value = undefined
      message.info(t("page.analysis.rerunHint"))
    })
  }
  catch (cause) {
    showError(cause)
  }
}
function prepareRerun() {
  if (!run.value || busy.value)
    return
  editorLoader.cancel()
  applyMethod(run.value.recipe, run.value.source_selection)
  question.value = run.value.question
  method.value = null
  pipelineRevisionId.value = undefined
  rerunOfId.value = run.value.id
  message.info(t("page.analysis.rerunHint"))
}
async function saveMethod() {
  if (!run.value || !methodTitle.value.trim())
    return
  busy.value = true
  try {
    await saveProjectAnalysisMethod(run.value.id, methodTitle.value.trim())
    saveVisible.value = false
    methodTitle.value = ""
    await refreshLists()
  }
  catch (cause) {
    showError(cause)
  }
  finally {
    busy.value = false
  }
}
function confirmRevision() {
  const saved = method.value
  if (!saved || !valid.value)
    return
  const payload = {
    recipe: clone(recipe.value),
    source_selection: clone(selection.value),
    expected_revision: saved.current_revision,
  }
  dialog.warning({
    title: t("page.analysis.saveRevision", { number: saved.current_revision + 1 }),
    content: t("page.analysis.revisionHint"),
    positiveText: t("common.confirm"),
    negativeText: t("common.cancel"),
    onPositiveClick: async () => {
      try {
        await reviseProjectAnalysisMethod(saved.id, payload)
        await loadMethod(saved.id)
        await refreshLists()
      }
      catch (cause) {
        showError(cause)
      }
    },
  })
}
function confirmCancel() {
  const current = run.value
  if (!current)
    return
  dialog.warning({
    title: t("page.analysis.cancelTitle"),
    content: t("page.analysis.cancelHint"),
    positiveText: t("common.confirm"),
    negativeText: t("common.cancel"),
    onPositiveClick: async () => {
      try {
        await cancelAnalysis(current.id)
        await openRun(current.id)
        await refreshLists()
      }
      catch (cause) {
        showError(cause)
      }
    },
  })
}
async function download() {
  if (!run.value)
    return
  try {
    const result = await downloadProjectAnalysis(run.value.id)
    downloadAs(
      JSON.stringify(result, null, 2),
      `project-analysis-${result.id}.json`,
      "application/json",
    )
  }
  catch (cause) {
    showError(cause)
  }
}
async function openSource(
  source: Pick<
    ProjectAnalysisRecordRef,
    "protocol_id" | "protocol_version" | "record_id" | "record_version"
  >,
) {
  try {
    const protocol = await getProtocolInfo(source.protocol_id)
    if (protocol.error || !protocol.data)
      throw protocol.error
    await router.push({
      name: "protocol-record-report",
      params: {
        labUid: route.params.labUid,
        projectUid: route.params.projectUid,
        protocolUid: protocol.data.uid,
        protocolVersion: source.protocol_version,
        recordId: source.record_id,
        recordVersion: String(source.record_version),
      },
    })
  }
  catch (cause) {
    showError(cause)
  }
}
watch(
  () => props.projectId,
  () => void initialize(),
  { immediate: true },
)
watch(() => route.query.runId, (id) => {
  if (typeof id === "string" && id !== run.value?.id)
    void openRun(id, false)
})
onBeforeUnmount(() => {
  editorLoader.cancel()
  sequence += 1
  runSequence += 1
  if (poll)
    clearTimeout(poll)
})
</script>

<style scoped>
.project-workbench {
  min-width: 0;
}
.workbench-grid {
  display: grid;
  grid-template-columns: minmax(0, 30rem) minmax(0, 1fr);
  gap: 20px;
  align-items: start;
}
.project-panel {
  min-width: 0;
  padding: 20px;
  border: 1px solid #e5e7eb;
  border-radius: 16px;
  background: white;
}
.source-card {
  min-width: 0;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  padding: 16px;
}
.history-item {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 12px;
  margin-bottom: 10px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  text-align: left;
  background: white;
  cursor: pointer;
  overflow-wrap: anywhere;
}
.history-item:hover {
  background: #f7f9fc;
}
.history-item:focus-visible {
  outline: 2px solid #0084e2;
  outline-offset: 2px;
}
.break-anywhere {
  overflow-wrap: anywhere;
}
.source-link {
  max-width: 100%;
  white-space: normal;
  height: auto;
  text-align: left;
}
.source-link :deep(.n-button__content) {
  white-space: normal;
  overflow-wrap: anywhere;
}
@media (max-width: 1150px) {
  .workbench-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
@media (max-width: 600px) {
  .project-panel {
    padding: 16px;
  }
  .source-card {
    padding: 12px;
  }
}
</style>
