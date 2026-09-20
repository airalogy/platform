<template>
  <section class="interpretation mt-6" data-testid="project-interpretation">
    <h3 class="aira-type-section-title">
      {{ t("page.projectAnalysis.interpretation.title") }}
    </h3>
    <n-alert type="info" class="mb-4">
      {{ t("page.projectAnalysis.interpretation.hint") }}
    </n-alert>
    <n-alert v-if="error" type="error" class="my-3">
      {{ error }}
    </n-alert>
    <n-spin :show="loading">
      <n-form label-placement="top" :disabled="busy || !authorized">
        <n-form-item :label="t('page.projectAnalysis.interpretation.judgement')" required>
          <n-select
            v-model:value="content.judgement"
            :options="relationOptions"
            data-testid="project-judgement"
          />
        </n-form-item>
        <n-form-item :label="t('page.projectAnalysis.interpretation.summary')" required>
          <n-input
            v-model:value="content.summary"
            type="textarea"
            :maxlength="8000"
            :autosize="{ minRows: 3, maxRows: 8 }"
            data-testid="project-judgement-summary"
          />
        </n-form-item>
        <article
          v-for="(finding, index) in content.findings"
          :key="index"
          class="finding mb-3"
          data-testid="project-finding"
        >
          <n-form-item :label="t('page.projectAnalysis.sourceSlot')">
            <n-select
              :value="finding.slot_id"
              :options="slotOptions"
              @update:value="value => changeSlot(index, value)"
            />
          </n-form-item>
          <n-form-item :label="t('page.analysis.field')">
            <n-select v-model:value="finding.field" :options="fieldOptions(finding.slot_id)" />
          </n-form-item>
          <n-form-item :label="t('page.projectAnalysis.interpretation.relation')">
            <n-select v-model:value="finding.relation" :options="relationOptions" />
          </n-form-item>
          <n-form-item :label="t('page.projectAnalysis.interpretation.note')" required>
            <n-input
              v-model:value="finding.note"
              type="textarea"
              :maxlength="4000"
              :autosize="{ minRows: 2, maxRows: 5 }"
              data-testid="project-finding-note"
            />
          </n-form-item>
          <n-button
            size="small"
            :disabled="content.findings.length <= 2"
            @click="content.findings.splice(index, 1)"
          >
            {{ t("common.delete") }}
          </n-button>
        </article>
        <n-button
          class="mb-4"
          size="small"
          :disabled="content.findings.length >= 40"
          @click="addFinding"
        >
          {{ t("page.projectAnalysis.interpretation.addFinding") }}
        </n-button>
        <n-form-item :label="t('page.projectAnalysis.interpretation.limitations')">
          <n-input
            v-model:value="limitations"
            type="textarea"
            :maxlength="8000"
            :autosize="{ minRows: 2, maxRows: 6 }"
          />
        </n-form-item>
        <n-form-item :label="t('page.projectAnalysis.interpretation.questions')">
          <n-input
            v-model:value="questions"
            type="textarea"
            :maxlength="8000"
            :autosize="{ minRows: 2, maxRows: 6 }"
          />
        </n-form-item>
        <n-button
          type="primary"
          :disabled="!valid || loading || !authorized"
          :loading="busy"
          data-testid="project-save-judgement"
          @click="confirmSave"
        >
          {{ t("page.projectAnalysis.interpretation.saveRevision", { number: revision + 1 }) }}
        </n-button>
      </n-form>
      <details
        v-if="history.length"
        class="aira-disclosure mt-4"
        data-testid="project-judgement-history"
      >
        <summary>
          {{
            t("page.projectAnalysis.interpretation.history", { count: history.length })
          }}
        </summary>
        <article v-for="item in history" :key="item.id" class="finding mb-3">
          <h4 class="aira-type-label">
            r{{ item.revision }} · {{ new Date(item.created_at).toLocaleString(locale) }}
          </h4>
          <p>
            {{ t(`page.projectAnalysis.relations.${item.content.judgement}`) }} —
            {{ item.content.summary }}
          </p>
          <ul class="pl-5">
            <li v-for="(finding, index) in item.content.findings" :key="index">
              {{
                slotOptions.find(slot => slot.value === finding.slot_id)?.label || finding.slot_id
              }}
              · {{ finding.field }} · {{ t(`page.projectAnalysis.relations.${finding.relation}`) }}:
              {{ finding.note }}
            </li>
          </ul>
          <p class="aira-type-meta break-anywhere">
            {{ t("page.projectAnalysis.interpretation.sealedResult") }}: {{ item.result_digest }}
          </p>
          <p
            v-for="(note, index) in item.content.limitations"
            :key="`limit-${index}`"
            class="aira-type-meta"
          >
            {{ note }}
          </p>
          <p
            v-for="(question, index) in item.content.unanswered_questions"
            :key="`question-${index}`"
            class="aira-type-meta"
          >
            {{ question }}
          </p>
        </article>
      </details>
    </n-spin>
  </section>
</template>

<script setup lang="ts">
import type {
  ProjectAnalysisRun,
  ProjectInterpretationContent,
  ProjectInterpretationRevision,
} from "@/service/api/project-analysis"
import {
  createProjectInterpretation,
  fetchProjectInterpretations,
} from "@/service/api/project-analysis"
import { useDialog } from "naive-ui"
import { useI18n } from "vue-i18n"

const props = defineProps<{ run: ProjectAnalysisRun }>()
const { t, locale } = useI18n()
const dialog = useDialog()
const content = ref<ProjectInterpretationContent>({
  judgement: "inconclusive",
  summary: "",
  findings: [],
  limitations: [],
  unanswered_questions: [],
})
const limitations = ref("")
const questions = ref("")
const revision = ref(0)
const history = ref<ProjectInterpretationRevision[]>([])
const loading = ref(false)
const authorized = ref(false)
const busy = ref(false)
const error = ref("")
let sequence = 0
const relationOptions = computed(() =>
  (["supports", "contradicts", "inconclusive"] as const).map(value => ({
    value,
    label: t(`page.projectAnalysis.relations.${value}`),
  })),
)
const slotOptions = computed(
  () =>
    props.run.result?.local_results.map(item => ({ value: item.slot_id, label: item.label })) || [],
)
function fieldOptions(slotId: string) {
  return (
    props.run.result?.local_results
      .find(item => item.slot_id === slotId)
      ?.report
      .fields
      .map(field => ({
        value: field.key,
        label: `${field.title || field.key}${field.unit ? ` (${field.unit})` : ""}`,
      })) || []
  )
}
const valid = computed(
  () =>
    content.value.summary.trim()
    && new Set(content.value.findings.map(finding => finding.slot_id)).size >= 2
    && content.value.findings.every(
      finding =>
        finding.note.trim()
        && fieldOptions(finding.slot_id).some(field => field.value === finding.field),
    ),
)
function changeSlot(index: number, value: string) {
  Object.assign(content.value.findings[index], {
    slot_id: value,
    field: fieldOptions(value)[0]?.value || "",
  })
}
function addFinding() {
  const id = slotOptions.value[0]?.value || ""
  content.value.findings.push({
    slot_id: id,
    field: fieldOptions(id)[0]?.value || "",
    relation: "inconclusive",
    note: "",
  })
}
function showError(cause: unknown) {
  const detail = (cause as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  error.value = typeof detail === "string" ? detail : t("page.analysis.requestError")
}
async function load() {
  const current = ++sequence
  loading.value = true
  error.value = ""
  history.value = []
  authorized.value = false
  content.value = { judgement: "inconclusive", summary: "", findings: [], limitations: [], unanswered_questions: [] }
  try {
    const result = await fetchProjectInterpretations(props.run.id)
    if (current !== sequence)
      return
    revision.value = result.current_revision
    history.value = result.items
    authorized.value = true
    const latest = result.items.find(item => item.revision === result.current_revision)
    content.value = latest
      ? JSON.parse(JSON.stringify(latest.content))
      : {
          judgement: "inconclusive",
          summary: "",
          findings: slotOptions.value.map(slot => ({
            slot_id: slot.value,
            field: fieldOptions(slot.value)[0]?.value || "",
            relation: "inconclusive",
            note: "",
          })),
          limitations: [],
          unanswered_questions: [],
        }
    limitations.value = content.value.limitations.join("\n")
    questions.value = content.value.unanswered_questions.join("\n")
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
function confirmSave() {
  if (!valid.value || !props.run.result_digest)
    return
  const id = props.run.id
  const payload = {
    expected_revision: revision.value,
    result_digest: props.run.result_digest,
    content: {
      ...(JSON.parse(JSON.stringify(content.value)) as ProjectInterpretationContent),
      limitations: limitations.value
        .split("\n")
        .map(value => value.trim())
        .filter(Boolean),
      unanswered_questions: questions.value
        .split("\n")
        .map(value => value.trim())
        .filter(Boolean),
    },
  }
  dialog.warning({
    title: t("page.projectAnalysis.interpretation.saveRevision", { number: revision.value + 1 }),
    content: t("page.projectAnalysis.interpretation.confirm"),
    positiveText: t("common.confirm"),
    negativeText: t("common.cancel"),
    onPositiveClick: async () => {
      busy.value = true
      try {
        await createProjectInterpretation(id, payload)
        await load()
      }
      catch (cause) {
        showError(cause)
      }
      finally {
        busy.value = false
      }
    },
  })
}
watch(
  () => props.run.id,
  () => void load(),
  { immediate: true },
)
onBeforeUnmount(() => {
  sequence += 1
})
</script>

<style scoped>
.interpretation {
  min-width: 0;
  border-top: 1px solid #e5e7eb;
  padding-top: 12px;
}
.finding {
  min-width: 0;
  padding: 12px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  overflow-wrap: anywhere;
}
.break-anywhere {
  overflow-wrap: anywhere;
}
</style>
