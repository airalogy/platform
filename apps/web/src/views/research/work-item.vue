<template>
  <div class="human-work-page py-8">
    <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
      <n-button quaternary @click="openTask">
        <template #icon><n-icon><icon-tabler-arrow-left /></n-icon></template>
        {{ $t("page.research.backToTask") }}
      </n-button>
      <n-button quaternary :loading="loading" @click="load">
        <template #icon><n-icon><icon-tabler-refresh /></n-icon></template>
        {{ $t("page.research.refresh") }}
      </n-button>
    </div>

    <n-alert v-if="loadError" type="error" :title="$t('page.research.loadError')">
      <n-button size="small" class="mt-2" @click="load">{{ $t("common.retry") }}</n-button>
    </n-alert>

    <n-spin v-else :show="loading && !item" class="min-h-80">
      <template v-if="item">
        <header class="human-work-hero">
          <div class="min-w-0 flex-1">
            <div class="flex flex-wrap items-center gap-2">
              <span class="aira-type-meta">{{ item.lab.name }} / {{ item.project.name }}</span>
              <n-tag data-testid="human-work-status" :type="statusType" round size="small">{{ statusLabel }}</n-tag>
              <n-tag round size="small">
                {{ isProtocolWork ? $t("page.research.protocolWork") : $t("page.research.structuredHumanWork") }}
              </n-tag>
            </div>
            <h1 class="aira-type-page-title mb-0 mt-2">{{ item.action.title }}</h1>
            <p class="aira-type-body aira-text-secondary mb-0 mt-3 whitespace-pre-wrap">
              {{ item.instructions }}
            </p>
            <div class="aira-type-meta mt-3 flex flex-wrap gap-x-4 gap-y-1">
              <span>{{ $t("page.research.partOfTask") }} · {{ item.task.title }}</span>
              <span>{{ $t("page.research.assignedTo") }} · {{ item.assignee.name || item.assignee.username }}</span>
              <span v-if="item.due_at">{{ $t("page.research.due") }} · {{ formatDateTime(item.due_at) }}</span>
            </div>
          </div>
          <n-button v-if="isProtocolWork && canOpenProtocol" type="primary" :loading="mutating" @click="openProtocolWork">
            {{ $t("page.research.executeProtocol") }}
          </n-button>
        </header>

        <n-alert v-if="changeReason" type="warning" class="mt-5" :title="$t('page.research.changesRequested')">
          {{ changeReason }}
        </n-alert>

        <template v-if="!isProtocolWork && contract">
          <div class="grid grid-cols-1 mt-6 gap-5 xl:grid-cols-[minmax(0,2fr)_minmax(17rem,1fr)]">
            <main class="space-y-5">
              <section class="human-work-panel">
                <div class="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div class="aira-type-eyebrow">{{ $t("page.research.structuredSubmission") }}</div>
                    <h2 class="aira-type-section-title mb-0 mt-1">{{ $t("page.research.requiredResults") }}</h2>
                  </div>
                  <div class="min-w-44">
                    <div class="aira-type-meta mb-1">{{ $t("page.research.requiredProgress", { completed: completedRequired, total: requiredCount }) }}</div>
                    <n-progress type="line" :percentage="completionPercentage" :show-indicator="false" />
                  </div>
                </div>

                <p v-if="contract.completion_criteria" class="human-work-criteria mt-4">
                  <strong>{{ $t("page.research.completionCriteria") }}</strong>
                  <span>{{ contract.completion_criteria }}</span>
                </p>

                <n-form label-placement="top" class="mt-5">
                  <n-form-item
                    v-for="field in contract.fields"
                    :key="field.key"
                    :data-testid="`human-work-field-${field.key}`"
                    :label="fieldLabel(field)"
                    :required="field.required"
                  >
                    <n-input
                      v-if="field.value_type === 'text' || field.value_type === 'long_text'"
                      :value="stringValue(field.key)"
                      :type="field.value_type === 'long_text' ? 'textarea' : 'text'"
                      :autosize="field.value_type === 'long_text' ? { minRows: 4, maxRows: 12 } : undefined"
                      :disabled="!item.permissions.can_submit"
                      @update:value="value => setValue(field.key, value)"
                    />
                    <n-input-number
                      v-else-if="field.value_type === 'number'"
                      :value="numberValue(field.key)"
                      :disabled="!item.permissions.can_submit"
                      class="w-full"
                      @update:value="value => setValue(field.key, value)"
                    >
                      <template v-if="field.unit" #suffix>{{ field.unit }}</template>
                    </n-input-number>
                    <n-radio-group
                      v-else-if="field.value_type === 'boolean'"
                      :value="booleanValue(field.key)"
                      :disabled="!item.permissions.can_submit"
                      @update:value="value => setValue(field.key, value)"
                    >
                      <n-space>
                        <n-radio :value="true">{{ $t("page.research.booleanYes") }}</n-radio>
                        <n-radio :value="false">{{ $t("page.research.booleanNo") }}</n-radio>
                      </n-space>
                    </n-radio-group>
                    <n-date-picker
                      v-else-if="field.value_type === 'date'"
                      :formatted-value="stringValue(field.key) || null"
                      value-format="yyyy-MM-dd"
                      type="date"
                      :disabled="!item.permissions.can_submit"
                      class="w-full"
                      @update:formatted-value="value => setValue(field.key, value)"
                    />
                    <n-select
                      v-else
                      :value="stringValue(field.key) || null"
                      :options="field.options.map(option => ({ label: option, value: option }))"
                      clearable
                      :disabled="!item.permissions.can_submit"
                      @update:value="value => setValue(field.key, value)"
                    />
                    <template v-if="field.description" #feedback>{{ field.description }}</template>
                  </n-form-item>

                  <n-form-item v-if="contract.data_asset_max_count" :label="$t('page.research.supportingDataAssets')">
                    <n-select
                      v-model:value="selectedAssetVersionIds"
                      :options="dataAssetOptions"
                      multiple
                      clearable
                      filterable
                      max-tag-count="responsive"
                      :disabled="!item.permissions.can_submit"
                      :placeholder="$t('page.research.selectSupportingDataAssets')"
                    />
                    <template #feedback>
                      {{ $t("page.research.dataAssetCountContract", {
                        minimum: contract.data_asset_min_count,
                        maximum: contract.data_asset_max_count,
                      }) }}
                    </template>
                  </n-form-item>

                  <n-form-item :label="$t('page.research.submissionNote')">
                    <n-input
                      v-model:value="note"
                      data-testid="human-work-submission-note"
                      type="textarea"
                      :autosize="{ minRows: 2, maxRows: 6 }"
                      :disabled="!item.permissions.can_submit"
                    />
                  </n-form-item>
                </n-form>

                <div v-if="item.permissions.can_submit" class="flex flex-wrap justify-end gap-2">
                  <n-button v-if="submissionPreview" @click="submissionPreview = null">
                    {{ $t("page.research.backToEdit") }}
                  </n-button>
                  <n-button v-if="!submissionPreview" data-testid="human-work-preview-submission" type="primary" :loading="mutating" @click="previewSubmission">
                    {{ $t("page.research.previewSubmission") }}
                  </n-button>
                  <n-button v-else data-testid="human-work-confirm-submission" type="primary" :loading="mutating" @click="confirmSubmission">
                    {{ $t("page.research.confirmSubmission") }}
                  </n-button>
                </div>
              </section>

              <section v-if="submissionPreview" class="human-work-panel human-work-panel--attention">
                <div class="aira-type-eyebrow">{{ $t("page.research.previewImpact") }}</div>
                <h2 class="aira-type-section-title mb-0 mt-1">{{ $t("page.research.submissionReady") }}</h2>
                <ul class="human-work-effects">
                  <li v-for="effect in submissionPreview.effects" :key="effect">{{ effect }}</li>
                </ul>
              </section>

              <section v-if="item.status === 'submitted'" class="human-work-panel human-work-panel--attention">
                <div class="aira-type-eyebrow">{{ $t("page.research.humanReview") }}</div>
                <h2 class="aira-type-section-title mb-0 mt-1">{{ $t("page.research.reviewSubmission") }}</h2>
                <n-alert v-if="!item.permissions.can_review" type="info" class="mt-4">
                  {{ $t("page.research.waitingForHumanReview") }}
                </n-alert>
                <template v-else>
                  <n-form label-placement="top" class="mt-4">
                    <n-form-item :label="$t('page.research.reviewDecision')" required>
                      <n-radio-group v-model:value="reviewDecision">
                        <n-space>
                          <n-radio value="accept">{{ $t("page.research.acceptSubmission") }}</n-radio>
                          <n-radio value="changes_requested">{{ $t("page.research.requestChanges") }}</n-radio>
                        </n-space>
                      </n-radio-group>
                    </n-form-item>
                    <n-form-item :label="$t('page.research.reviewReason')" :required="reviewDecision === 'changes_requested'">
                      <n-input v-model:value="reviewReason" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" />
                    </n-form-item>
                  </n-form>
                  <div v-if="reviewPreview" class="human-work-review-preview mb-4">
                    <strong class="aira-type-label">{{ $t("page.research.previewImpact") }}</strong>
                    <ul class="human-work-effects">
                      <li v-for="effect in reviewPreview.effects" :key="effect">{{ effect }}</li>
                    </ul>
                  </div>
                  <div class="flex flex-wrap justify-end gap-2">
                    <n-button v-if="reviewPreview" @click="reviewPreview = null">{{ $t("page.research.backToEdit") }}</n-button>
                    <n-button v-if="!reviewPreview" data-testid="human-work-preview-review" type="primary" :disabled="reviewDecision === 'changes_requested' && !reviewReason.trim()" :loading="mutating" @click="previewReview">
                      {{ $t("page.research.previewReview") }}
                    </n-button>
                    <n-button v-else data-testid="human-work-confirm-review" type="primary" :loading="mutating" @click="confirmReview">
                      {{ reviewDecision === "accept" ? $t("page.research.confirmAcceptance") : $t("page.research.confirmChanges") }}
                    </n-button>
                  </div>
                </template>
              </section>

              <n-result v-if="item.status === 'accepted'" status="success" :title="$t('page.research.humanWorkAccepted')">
                <template #footer>
                  <n-button type="primary" @click="openTask">{{ $t("page.research.viewTask") }}</n-button>
                </template>
              </n-result>
            </main>

            <aside class="space-y-5">
              <section class="human-work-panel">
                <div class="aira-type-eyebrow">{{ $t("page.research.submissionContract") }}</div>
                <dl class="human-work-facts mt-3">
                  <div>
                    <dt>{{ $t("page.research.evidenceKind") }}</dt>
                    <dd>{{ evidenceKindLabel(contract.evidence_kind) }}</dd>
                  </div>
                  <div>
                    <dt>{{ $t("page.research.submissionFields") }}</dt>
                    <dd>{{ contract.fields.length }}</dd>
                  </div>
                  <div>
                    <dt>{{ $t("page.research.supportingDataAssets") }}</dt>
                    <dd>{{ contract.data_asset_min_count }}–{{ contract.data_asset_max_count }}</dd>
                  </div>
                </dl>
              </section>
              <section v-if="submittedAssets.length" class="human-work-panel">
                <div class="aira-type-eyebrow">{{ $t("page.research.linkedDataAssets") }}</div>
                <div class="mt-3 space-y-2">
                  <div v-for="asset in submittedAssets" :key="asset.data_asset_version_id" class="human-work-asset">
                    <strong class="aira-type-label">{{ asset.name }}</strong>
                    <span class="aira-type-meta">v{{ asset.version }} · {{ asset.kind }}</span>
                  </div>
                </div>
              </section>
              <section class="human-work-panel">
                <div class="aira-type-eyebrow">{{ $t("page.research.governance") }}</div>
                <p class="aira-type-meta mb-0 mt-3">{{ $t("page.research.humanWorkGovernanceHint") }}</p>
              </section>
            </aside>
          </div>
        </template>

        <n-empty v-else-if="!isProtocolWork" class="mt-6 py-12" :description="$t('page.research.invalidHumanWorkContract')" />
      </template>
    </n-spin>
  </div>
</template>

<script setup lang="ts">
import type { DataAsset } from "@/service/api/research-assets"
import type {
  HumanWorkCommandPreview,
  HumanWorkField,
  HumanWorkSubmission,
  HumanWorkSubmissionContract,
  ResearchWorkItemDetail,
} from "@/service/api/research-tasks"
import type { TagProps } from "naive-ui"
import { fetchResearchAssets } from "@/service/api/research-assets"
import {
  fetchResearchWorkItem,
  previewHumanWorkReview,
  previewHumanWorkSubmission,
  reviewHumanWork,
  startResearchWorkItem,
  submitHumanWork,
} from "@/service/api/research-tasks"
import { useAuthStore } from "@/store/modules/auth"
import { $t } from "@airalogy/shared/locales"
import { useRoute, useRouter } from "vue-router"

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const item = ref<ResearchWorkItemDetail | null>(null)
const assets = ref<DataAsset[]>([])
const loading = ref(false)
const loadError = ref(false)
const mutating = ref(false)
const values = ref<Record<string, unknown>>({})
const selectedAssetVersionIds = ref<string[]>([])
const note = ref("")
const submissionPreview = ref<HumanWorkCommandPreview | null>(null)
const reviewPreview = ref<HumanWorkCommandPreview | null>(null)
const reviewDecision = ref<"accept" | "changes_requested">("accept")
const reviewReason = ref("")

const isProtocolWork = computed(() => item.value?.action.kind === "protocol_run")
const contract = computed<HumanWorkSubmissionContract | null>(() => {
  const value = item.value?.submission_contract as Partial<HumanWorkSubmissionContract> | undefined
  return value?.schema === "airalogy.human-work-submission.v1"
    && value.type === "structured_values"
    && Array.isArray(value.fields)
    ? value as HumanWorkSubmissionContract
    : null
})
const submission = computed(() => (item.value?.submission || {}) as HumanWorkSubmission)
const submittedAssets = computed(() => submission.value.data_assets || [])
const requiredFields = computed(() => contract.value?.fields.filter(field => field.required) || [])
const requiredCount = computed(() => requiredFields.value.length)
const completedRequired = computed(() => requiredFields.value.filter(field => hasValue(values.value[field.key])).length)
const completionPercentage = computed(() => requiredCount.value
  ? Math.round((completedRequired.value / requiredCount.value) * 100)
  : 100)
const statusLabel = computed(() => item.value
  ? $t(`page.research.workItemStatus.${item.value.status}` as I18n.I18nKey)
  : "")
const statusType = computed<TagProps["type"]>(() => {
  if (item.value?.status === "accepted")
    return "success"
  if (item.value?.status === "changes_requested")
    return "warning"
  if (item.value?.status === "cancelled")
    return "error"
  return "info"
})
const changeReason = computed(() => {
  if (item.value?.status !== "changes_requested")
    return ""
  const issue = item.value.validation_issues?.[0]
  return String(issue?.message || submission.value.review?.reason || "")
})
const canOpenProtocol = computed(() => Boolean(
  item.value?.action.protocol
  && String(item.value.assignee.id) === String(authStore.userInfo.id)
  && ["open", "in_progress", "changes_requested"].includes(item.value.status),
))
const dataAssetOptions = computed(() => assets.value.flatMap((asset) => {
  if (!["draft", "ready"].includes(asset.status))
    return []
  const version = asset.versions.find(item => item.version === asset.current_version)
  return version
    ? [{
        value: version.id,
        label: `${asset.name} · v${version.version} · ${asset.kind}`,
      }]
    : []
}))

function hasValue(value: unknown) {
  return value !== null && value !== undefined && (!(typeof value === "string") || Boolean(value.trim()))
}

function stringValue(key: string) {
  const value = values.value[key]
  return typeof value === "string" ? value : ""
}

function numberValue(key: string) {
  const value = values.value[key]
  return typeof value === "number" ? value : null
}

function booleanValue(key: string) {
  const value = values.value[key]
  return typeof value === "boolean" ? value : null
}

function setValue(key: string, value: unknown) {
  values.value = { ...values.value, [key]: value }
  submissionPreview.value = null
}

function fieldLabel(field: HumanWorkField) {
  return field.unit ? `${field.label} (${field.unit})` : field.label
}

function evidenceKindLabel(kind: HumanWorkSubmissionContract["evidence_kind"]) {
  return $t(`page.research.evidenceKindValue.${kind}` as I18n.I18nKey)
}

function formatDateTime(value: string) {
  return new Date(value).toLocaleString()
}

function syncSubmission() {
  const current = submission.value
  values.value = { ...(current.values || {}) }
  selectedAssetVersionIds.value = (current.data_assets || []).map(asset => asset.data_asset_version_id)
  note.value = current.note || ""
  submissionPreview.value = null
  reviewPreview.value = null
}

async function load() {
  loading.value = true
  loadError.value = false
  try {
    item.value = await fetchResearchWorkItem(String(route.params.workItemId))
    syncSubmission()
    if (!isProtocolWork.value && contract.value?.data_asset_max_count)
      assets.value = (await fetchResearchAssets(item.value.task.id)).data_assets
  }
  catch {
    loadError.value = true
  }
  finally {
    loading.value = false
  }
}

function openTask() {
  if (item.value)
    void router.push({ name: "research-task-detail", params: { taskId: item.value.task.id } })
  else
    void router.push({ name: "research-work-items" })
}

async function ensureStarted() {
  if (!item.value || !["open", "changes_requested"].includes(item.value.status))
    return
  item.value = await startResearchWorkItem(item.value.id, item.value.revision)
}

async function openProtocolWork() {
  if (!item.value?.action.protocol)
    return
  mutating.value = true
  try {
    await ensureStarted()
    const protocol = item.value.action.protocol
    await router.push({
      name: "add-protocol-record",
      params: {
        labUid: protocol.lab_uid || item.value.lab.uid,
        projectUid: protocol.project_uid || item.value.project.uid,
        protocolUid: protocol.uid,
      },
      query: { researchWorkItem: item.value.id },
    })
  }
  finally {
    mutating.value = false
  }
}

function submissionPayload() {
  if (!item.value)
    throw new Error("Human Work Item is unavailable")
  return {
    expected_revision: item.value.revision,
    values: values.value,
    data_asset_version_ids: selectedAssetVersionIds.value,
    note: note.value.trim(),
  }
}

async function previewSubmission() {
  if (!item.value)
    return
  mutating.value = true
  try {
    await ensureStarted()
    submissionPreview.value = await previewHumanWorkSubmission(item.value.id, submissionPayload())
  }
  finally {
    mutating.value = false
  }
}

async function confirmSubmission() {
  if (!item.value || !submissionPreview.value)
    return
  mutating.value = true
  try {
    item.value = await submitHumanWork(item.value.id, {
      ...submissionPayload(),
      preview_digest: submissionPreview.value.preview_digest,
    })
    syncSubmission()
    window.$message?.success($t("page.research.humanWorkSubmitted"))
  }
  finally {
    mutating.value = false
  }
}

function reviewPayload() {
  if (!item.value)
    throw new Error("Human Work Item is unavailable")
  return {
    expected_revision: item.value.revision,
    expected_action_revision: item.value.action.revision,
    decision: reviewDecision.value,
    reason: reviewReason.value.trim(),
  }
}

async function previewReview() {
  if (!item.value)
    return
  mutating.value = true
  try {
    reviewPreview.value = await previewHumanWorkReview(item.value.id, reviewPayload())
  }
  finally {
    mutating.value = false
  }
}

async function confirmReview() {
  if (!item.value || !reviewPreview.value)
    return
  mutating.value = true
  try {
    item.value = await reviewHumanWork(item.value.id, {
      ...reviewPayload(),
      preview_digest: reviewPreview.value.preview_digest,
    })
    syncSubmission()
    window.$message?.success(reviewDecision.value === "accept"
      ? $t("page.research.humanWorkAccepted")
      : $t("page.research.humanWorkChangesRequested"))
  }
  finally {
    mutating.value = false
  }
}

watch([reviewDecision, reviewReason], () => {
  reviewPreview.value = null
})
onMounted(load)
</script>

<style scoped>
.human-work-page {
  width: 100%;
}

.human-work-hero,
.human-work-panel {
  border: 1px solid rgb(229 231 235);
  border-radius: 1rem;
  background: white;
  padding: clamp(1.15rem, 2.5vw, 1.75rem);
}

.human-work-hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1.5rem;
  border-color: rgb(219 234 254);
  background: linear-gradient(135deg, rgb(var(--primary-color) / 8%), white 70%);
}

.human-work-panel--attention {
  border-color: rgb(var(--primary-color) / 28%);
  background: rgb(var(--primary-color) / 3%);
}

.human-work-criteria,
.human-work-review-preview {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  border-radius: 0.75rem;
  background: rgb(248 250 252);
  padding: 0.85rem 1rem;
  color: rgb(75 85 99);
}

.human-work-effects {
  margin: 0.75rem 0 0;
  padding-left: 1.25rem;
  color: rgb(75 85 99);
}

.human-work-effects li + li {
  margin-top: 0.35rem;
}

.human-work-facts {
  display: grid;
  gap: 0.8rem;
  margin-bottom: 0;
}

.human-work-facts > div,
.human-work-asset {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  border-radius: 0.7rem;
  background: rgb(248 250 252);
  padding: 0.75rem;
}

.human-work-facts dt {
  color: rgb(107 114 128);
  font-size: 0.75rem;
}

.human-work-facts dd {
  margin: 0;
  font-weight: 600;
}

@media (max-width: 48rem) {
  .human-work-hero {
    flex-direction: column;
  }
}
</style>
