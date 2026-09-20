<template>
  <section class="publication-panel mt-5" data-testid="analysis-publication-panel">
    <h3 class="aira-type-section-title">
      {{ t('page.analysisPublication.title') }}
    </h3>
    <p class="aira-type-meta">
      {{ t('page.analysisPublication.description') }}
    </p>
    <n-button :loading="loading" data-testid="analysis-publication-open" @click="open">
      {{ t('page.analysisPublication.open') }}
    </n-button>
    <n-alert v-if="result" type="success" class="mt-3" data-testid="analysis-publication-saved">
      {{ t('page.analysisPublication.saved', { title: result.title }) }}
      <p class="aira-type-meta break-anywhere">
        {{ t('page.analysisPublication.receipt') }} · {{ result.id }}
      </p>
      <n-button size="small" class="mt-2" @click="router.push(`/research/tasks/${result.task_id}`)">
        {{ t('page.analysisPublication.openTask') }}
      </n-button>
    </n-alert>
    <n-alert v-if="error && !visible" type="error" class="mt-3">
      {{ error }}
    </n-alert>
    <n-modal v-model:show="visible" preset="card" class="aira-dialog" style="--aira-dialog-width: 64rem" :title="t('page.analysisPublication.title')" :mask-closable="false" :closable="!busy" data-testid="analysis-publication-dialog">
      <n-alert v-if="error" type="error" class="mb-3">
        {{ error }}
      </n-alert>
      <n-spin :show="loading">
        <template v-if="preview">
          <div ref="previewStart" />
          <n-alert type="info" class="mb-3" data-testid="analysis-publication-destination">
            {{ t('page.analysisPublication.destination', { project: preview.destination.project_name, task: preview.destination.task_title }) }}
          </n-alert>
          <p>{{ t('page.analysisPublication.permissions') }}</p>
          <p>{{ t('page.analysisPublication.knowledgeNotice') }}</p>
          <analysis-publication-report :snapshot="preview.publication" />
          <p class="aira-type-meta mt-4">
            {{ t('page.analysisPublication.expires', { time: new Date(preview.expires_at).toLocaleString(locale) }) }}
          </p>
          <div class="mt-4 flex flex-wrap gap-2">
            <n-button :disabled="busy" @click="preview = null">
              {{ t('page.analysisPublication.edit') }}
            </n-button>
            <n-button type="primary" :loading="busy" :disabled="expired && !confirmationAttempted" data-testid="analysis-publication-confirm" @click="confirm">
              {{ t('page.analysisPublication.confirm') }}
            </n-button>
          </div>
          <n-alert v-if="expired" type="warning" class="mt-3">
            {{ t(confirmationAttempted ? 'page.analysisPublication.expiredRetry' : 'page.analysisPublication.expired') }}
          </n-alert>
        </template>
        <n-form v-else-if="context" label-placement="top" :disabled="busy || loading">
          <n-alert type="info" class="mb-3">
            {{ t('page.analysisPublication.permissions') }}
          </n-alert>
          <n-form-item :label="t('page.analysisPublication.task')" required>
            <n-select v-model:value="draft.task_id" :options="taskOptions" filterable data-testid="analysis-publication-task" />
          </n-form-item>
          <n-button v-if="context.next_task_offset !== null" size="small" :loading="loading" class="mb-3" @click="moreTasks">
            {{ t('page.analysisPublication.moreTasks') }}
          </n-button>
          <n-alert v-if="!context.tasks.length" type="warning" class="mb-3">
            {{ t('page.analysisPublication.noTasks') }}
          </n-alert>
          <n-form-item :label="t('page.analysisPublication.name')" required>
            <n-input v-model:value="draft.title" :maxlength="255" data-testid="analysis-publication-name" />
          </n-form-item>
          <n-form-item :label="t('page.analysisPublication.summary')">
            <n-input v-model:value="draft.summary" type="textarea" :maxlength="8000" :autosize="{ minRows: 2, maxRows: 5 }" data-testid="analysis-publication-summary" />
          </n-form-item>
          <p class="aira-type-meta">
            {{ t('page.analysisPublication.selectionHint') }}
          </p>
          <n-form-item v-for="(section, index) in context.sections" :key="section.section_id" :label="section.label">
            <n-select v-model:value="draft.sections[index].fields" :options="fieldOptions(section.fields)" multiple clearable data-testid="analysis-publication-fields" />
          </n-form-item>
          <n-form-item v-if="context.interpretations.length" :label="t('page.analysisPublication.humanInterpretation')">
            <n-select v-model:value="draft.interpretation_revision_id" :options="interpretationOptions" clearable data-testid="analysis-publication-interpretation-select" />
            <template #feedback>
              {{ t('page.analysisPublication.interpretationHint') }}
            </template>
          </n-form-item>
          <n-button type="primary" :disabled="!valid" :loading="busy" data-testid="analysis-publication-preview" @click="preparePreview">
            {{ t('page.analysisPublication.preview') }}
          </n-button>
        </n-form>
      </n-spin>
    </n-modal>
  </section>
</template>

<script setup lang="ts">
import type { AnalysisField } from "@/service/api/analysis"
import type { AnalysisPublication, AnalysisPublicationContext, AnalysisPublicationDraft, AnalysisPublicationPreview } from "@/service/api/analysis-publications"
import { confirmAnalysisPublication, fetchAnalysisPublicationContext, previewAnalysisPublication } from "@/service/api/analysis-publications"
import { analysisPublicationCommand, publicationConfirmationKey } from "@/utils/analysis-publications"
import { useNow } from "@vueuse/core"
import { useI18n } from "vue-i18n"
import { useRouter } from "vue-router"
import AnalysisPublicationReport from "./analysis-publication-report.vue"

const props = defineProps<{ analysisId: string }>()
const { t, locale } = useI18n()
const router = useRouter()
const visible = ref(false)
const loading = ref(false)
const busy = ref(false)
const error = ref("")
const context = ref<AnalysisPublicationContext | null>(null)
const preview = ref<AnalysisPublicationPreview | null>(null)
const result = ref<AnalysisPublication | null>(null)
const previewStart = ref<HTMLElement | null>(null)
const confirmationAttempted = ref(false)
const draft = reactive<AnalysisPublicationDraft>({ task_id: "", title: "", summary: "", sections: [], interpretation_revision_id: null })
let prepared: AnalysisPublicationDraft | null = null
let idempotencyKey = ""
let requestEpoch = 0
const now = useNow({ interval: 1000 })
const expired = computed(() => !preview.value || new Date(preview.value.expires_at).getTime() <= now.value.getTime())
const valid = computed(() => Boolean(draft.task_id && draft.title.trim() && draft.sections.some(section => section.fields.length)))
const taskOptions = computed(() => context.value?.tasks.map(task => ({ value: task.id, label: task.title })) || [])
const interpretationOptions = computed(() => context.value?.interpretations.map(item => ({ value: item.id, label: `r${item.revision} · ${item.summary}` })) || [])
function fieldOptions(fields: AnalysisField[]) {
  return fields.map(field => ({ value: field.key, label: `${field.title || field.key}${field.unit ? ` (${field.unit})` : ""}` }))
}

watch(() => props.analysisId, () => {
  requestEpoch += 1
  visible.value = false
  busy.value = false
  loading.value = false
  preview.value = null
  context.value = null
  result.value = null
  confirmationAttempted.value = false
  error.value = ""
})
onBeforeUnmount(() => {
  requestEpoch += 1
})
watch(preview, async (value) => {
  if (!value)
    return
  await nextTick()
  previewStart.value?.scrollIntoView({ block: "start" })
})

async function open() {
  const epoch = ++requestEpoch
  visible.value = true
  loading.value = true
  error.value = ""
  preview.value = null
  context.value = null
  const { data, error: failed } = await fetchAnalysisPublicationContext(props.analysisId)
  if (epoch !== requestEpoch)
    return
  loading.value = false
  if (failed || !data) {
    error.value = t("page.analysisPublication.loadError")
    return
  }
  context.value = data
  Object.assign(draft, {
    task_id: data.tasks.length === 1 ? data.tasks[0].id : "",
    title: "",
    summary: "",
    interpretation_revision_id: null,
    sections: data.sections.map(section => ({ section_id: section.section_id, fields: section.fields.map(field => field.key) })),
  })
}

async function moreTasks() {
  if (!context.value || context.value.next_task_offset === null)
    return
  const epoch = requestEpoch
  loading.value = true
  const { data, error: failed } = await fetchAnalysisPublicationContext(props.analysisId, context.value.next_task_offset)
  if (epoch !== requestEpoch)
    return
  loading.value = false
  if (failed || !data) {
    error.value = t("page.analysisPublication.loadError")
    return
  }
  const tasks = new Map(context.value.tasks.map(task => [task.id, task]))
  data.tasks.forEach(task => tasks.set(task.id, task))
  context.value.tasks = [...tasks.values()]
  context.value.next_task_offset = data.next_task_offset
}

async function preparePreview() {
  if (!valid.value || busy.value)
    return
  const epoch = requestEpoch
  busy.value = true
  error.value = ""
  const command = analysisPublicationCommand(draft)
  const { data, error: failed } = await previewAnalysisPublication(props.analysisId, command)
  if (epoch !== requestEpoch)
    return
  busy.value = false
  if (failed || !data) {
    error.value = t("page.analysisPublication.previewError")
    return
  }
  preview.value = data
  prepared = command
  idempotencyKey = publicationConfirmationKey()
  confirmationAttempted.value = false
}

async function confirm() {
  if (!preview.value || !prepared || busy.value || (expired.value && !confirmationAttempted.value))
    return
  const epoch = requestEpoch
  busy.value = true
  error.value = ""
  confirmationAttempted.value = true
  const { data, error: failed } = await confirmAnalysisPublication(props.analysisId, {
    ...prepared,
    preview_digest: preview.value.preview_digest,
    preview_token: preview.value.preview_token,
    client_idempotency_key: idempotencyKey,
  })
  if (epoch !== requestEpoch)
    return
  busy.value = false
  if (failed || !data) {
    error.value = t("page.analysisPublication.confirmError")
    return
  }
  result.value = data.publication
  visible.value = false
  preview.value = null
}
</script>
