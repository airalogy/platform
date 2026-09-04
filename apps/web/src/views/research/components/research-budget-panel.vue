<template>
  <section class="research-panel">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <div class="aira-type-eyebrow">
          {{ $t("page.research.operationalLimits") }}
        </div>
        <h2 class="aira-type-card-title mb-0 mt-1">
          {{ $t("page.research.timeAndBudget") }}
        </h2>
      </div>
      <div v-if="canManage" class="flex flex-wrap gap-2">
        <n-button v-if="canAmend" size="small" secondary @click="openAmendment">
          {{ $t("page.research.amendOperationalLimits") }}
        </n-button>
        <n-button
          v-if="currentBudgetLimit"
          size="small"
          secondary
          @click="entryVisible = true"
        >
          {{ $t("page.research.recordBudgetEntry") }}
        </n-button>
      </div>
    </div>

    <n-alert v-if="budgetError" type="error" class="mt-4">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <span>{{ $t("page.research.budgetLoadError") }}</span>
        <n-button size="tiny" @click="loadBudget">
          {{ $t("common.retry") }}
        </n-button>
      </div>
    </n-alert>

    <div class="mt-4 space-y-4">
      <div>
        <div class="aira-type-meta">
          {{ $t("page.research.deadline") }}
        </div>
        <div class="aira-type-label mt-1">
          {{ currentDeadlineAt ? new Date(currentDeadlineAt).toLocaleString() : $t("page.research.noLimit") }}
        </div>
      </div>
      <div v-if="currentBudgetLimit">
        <n-spin :show="budgetLoading">
          <div class="flex items-center justify-between gap-3">
            <span class="aira-type-meta">{{ $t("page.research.budgetCommitted") }}</span>
            <span class="aira-type-label">
              {{ budget?.committed || "0" }} / {{ currentBudgetLimit }} {{ currentBudgetCurrency }}
            </span>
          </div>
          <n-progress class="mt-2" type="line" :percentage="budgetPercentage" :show-indicator="false" />
          <div class="aira-type-meta mt-2 flex flex-wrap justify-between gap-2">
            <span>{{ $t("page.research.budgetReserved") }} · {{ budget?.reserved || "0" }}</span>
            <span>{{ $t("page.research.budgetActual") }} · {{ budget?.actual || "0" }}</span>
            <span>{{ $t("page.research.budgetRemaining") }} · {{ budget?.remaining ?? currentBudgetLimit }}</span>
          </div>
        </n-spin>
      </div>
      <p v-else class="aira-type-meta aira-text-muted mb-0">
        {{ $t("page.research.noBudgetLimit") }}
      </p>
    </div>

    <n-collapse v-if="budget?.entries.length" class="mt-4">
      <n-collapse-item :title="$t('page.research.budgetLedger')" name="ledger">
        <div class="space-y-2">
          <div v-for="entry in budget.entries" :key="entry.id" class="research-budget-entry">
            <div class="flex flex-wrap items-center justify-between gap-2">
              <n-tag size="small" round>
                {{ budgetKindLabel(entry.kind) }}
              </n-tag>
              <span class="aira-type-label">{{ entry.amount }} {{ entry.currency }}</span>
            </div>
            <p class="aira-type-meta mb-0 mt-1">
              {{ entry.description }}
            </p>
          </div>
        </div>
      </n-collapse-item>
    </n-collapse>

    <n-collapse v-if="limits?.amendments.length" class="mt-3">
      <n-collapse-item :title="$t('page.research.operationalLimitHistory')" name="limit-history">
        <div class="space-y-2">
          <div
            v-for="amendment in limits?.amendments"
            :key="amendment.id"
            class="research-budget-entry"
          >
            <div class="flex flex-wrap items-center justify-between gap-2">
              <span class="aira-type-label">{{ amendment.payload.reason }}</span>
              <span class="aira-type-meta">{{ new Date(amendment.created_at).toLocaleString() }}</span>
            </div>
            <p class="aira-type-meta mb-0 mt-1">
              {{ limitSummary(amendment.payload.current) }}
              → {{ limitSummary(amendment.payload.projected) }}
            </p>
          </div>
        </div>
      </n-collapse-item>
    </n-collapse>
  </section>

  <n-modal
    v-model:show="entryVisible"
    preset="card"
    class="research-budget-modal"
    :title="$t('page.research.recordBudgetEntry')"
    :mask-closable="false"
    @after-leave="reset"
  >
    <template v-if="!preview">
      <n-alert type="info" class="mb-4">
        {{ $t("page.research.budgetEntryHint") }}
      </n-alert>
      <n-form label-placement="top">
        <n-form-item :label="$t('page.research.budgetEntryKind')" required>
          <n-select v-model:value="kind" :options="kindOptions" />
        </n-form-item>
        <n-form-item :label="$t('page.research.amount')" required>
          <n-input-group>
            <n-input v-model:value="amount" inputmode="decimal" />
            <n-input-group-label>{{ currentBudgetCurrency }}</n-input-group-label>
          </n-input-group>
        </n-form-item>
        <n-form-item :label="$t('page.research.budgetDescription')" required>
          <n-input v-model:value="description" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" />
        </n-form-item>
      </n-form>
    </template>
    <template v-else>
      <n-alert type="warning">
        {{ preview.effect }}
      </n-alert>
      <div class="research-budget-preview mt-4">
        <div class="aira-type-meta">
          {{ $t("page.research.afterConfirmation") }}
        </div>
        <div class="aira-type-body mt-2 space-y-1">
          <div>{{ $t("page.research.budgetCommitted") }} · {{ preview.projected.committed }} {{ currentBudgetCurrency }}</div>
          <div>{{ $t("page.research.budgetRemaining") }} · {{ preview.projected.remaining }} {{ currentBudgetCurrency }}</div>
        </div>
      </div>
    </template>
    <template #footer>
      <div class="flex justify-end gap-2">
        <n-button @click="preview ? preview = null : entryVisible = false">
          {{ preview ? $t("page.research.backToEdit") : $t("common.cancel") }}
        </n-button>
        <n-button
          v-if="!preview"
          type="primary"
          :disabled="!valid"
          :loading="submitting"
          @click="handlePreview"
        >
          {{ $t("page.research.previewBudgetEntry") }}
        </n-button>
        <n-button v-else type="primary" :loading="submitting" @click="handleCreate">
          {{ $t("page.research.confirmBudgetEntry") }}
        </n-button>
      </div>
    </template>
  </n-modal>

  <n-modal
    v-model:show="amendmentVisible"
    preset="card"
    class="research-budget-modal"
    :title="$t('page.research.amendOperationalLimits')"
    :mask-closable="false"
    @after-leave="resetAmendment"
  >
    <template v-if="!limitPreview">
      <n-alert type="info" class="mb-4">
        {{ $t("page.research.operationalLimitAmendmentHint") }}
      </n-alert>
      <n-form label-placement="top">
        <n-form-item
          :label="$t('page.research.deadline')"
          :validation-status="amendmentDeadlineInvalid ? 'error' : undefined"
          :feedback="amendmentDeadlineInvalid ? $t('page.research.deadlineFuture') : undefined"
        >
          <n-date-picker
            v-model:value="amendedDeadlineAt"
            type="datetime"
            clearable
            class="w-full"
            :placeholder="$t('page.research.deadlinePlaceholder')"
            :is-date-disabled="isDeadlineDisabled"
          />
        </n-form-item>
        <n-form-item
          :label="$t('page.research.budgetLimit')"
          :validation-status="amendmentBudgetInvalid ? 'error' : undefined"
          :feedback="amendmentBudgetInvalid ? $t('page.research.budgetAmendmentInvalid') : undefined"
        >
          <n-input-group>
            <n-input
              v-model:value="amendedBudgetLimit"
              inputmode="decimal"
              clearable
              :placeholder="$t('page.research.budgetLimitPlaceholder')"
            />
            <n-select
              v-model:value="amendedBudgetCurrency"
              class="w-28"
              :options="currencyOptions"
              filterable
              tag
              :disabled="!amendedBudgetLimit || Boolean(budget?.entries.length)"
            />
          </n-input-group>
        </n-form-item>
        <n-alert v-if="budget?.entries.length" type="warning" class="mb-4">
          {{ $t("page.research.budgetCurrencyLocked") }}
        </n-alert>
        <n-form-item :label="$t('page.research.amendmentReason')" required>
          <n-input
            v-model:value="amendmentReason"
            type="textarea"
            :autosize="{ minRows: 3, maxRows: 8 }"
            :placeholder="$t('page.research.amendmentReasonPlaceholder')"
          />
        </n-form-item>
      </n-form>
    </template>
    <template v-else>
      <n-alert type="warning">
        {{ limitPreview.effect }}
      </n-alert>
      <div class="research-budget-preview mt-4 space-y-3">
        <div>
          <div class="aira-type-meta">
            {{ $t("page.research.currentLimits") }}
          </div>
          <div class="aira-type-body mt-1">
            {{ limitSummary(limitPreview.current) }}
          </div>
        </div>
        <div>
          <div class="aira-type-meta">
            {{ $t("page.research.afterConfirmation") }}
          </div>
          <div class="aira-type-body mt-1">
            {{ limitSummary(limitPreview.projected) }}
          </div>
        </div>
      </div>
      <n-alert v-if="limitPreview.resume_required" type="info" class="mt-4">
        {{ $t("page.research.resumeAfterAmendment") }}
      </n-alert>
    </template>
    <template #footer>
      <div class="flex justify-end gap-2">
        <n-button @click="limitPreview ? limitPreview = null : amendmentVisible = false">
          {{ limitPreview ? $t("page.research.backToEdit") : $t("common.cancel") }}
        </n-button>
        <n-button
          v-if="!limitPreview"
          type="primary"
          :disabled="!amendmentValid"
          :loading="amendmentSubmitting"
          @click="handleLimitPreview"
        >
          {{ $t("page.research.previewOperationalLimits") }}
        </n-button>
        <n-button
          v-else
          type="primary"
          :loading="amendmentSubmitting"
          @click="handleAmendment"
        >
          {{ $t("page.research.confirmOperationalLimits") }}
        </n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import type {
  ResearchBudgetEntryDraft,
  ResearchBudgetEntryKind,
  ResearchBudgetPreview,
  ResearchBudgetSnapshot,
  ResearchOperationalLimitsDraft,
  ResearchOperationalLimitsPreview,
  ResearchOperationalLimitsSnapshot,
  ResearchOperationalLimitValues,
} from "@/service/api/research-budget"
import {
  amendResearchOperationalLimits,
  createResearchBudgetEntry,
  fetchResearchOperationalLimits,
  previewResearchBudgetEntry,
  previewResearchOperationalLimits,
} from "@/service/api/research-budget"
import { $t } from "@airalogy/shared/locales"
import Big from "big.js"
import { nanoid } from "nanoid"

const props = defineProps<{
  taskId: string
  taskRevision: number
  deadlineAt?: string | null
  budgetLimit?: string | null
  budgetCurrency?: string | null
  canManage: boolean
  canAmend: boolean
}>()
const emit = defineEmits<{ changed: [] }>()

const budget = ref<ResearchBudgetSnapshot | null>(null)
const limits = ref<ResearchOperationalLimitsSnapshot | null>(null)
const budgetLoading = ref(false)
const budgetError = ref(false)
const entryVisible = ref(false)
const submitting = ref(false)
const preview = ref<ResearchBudgetPreview | null>(null)
const kind = ref<ResearchBudgetEntryKind>("reserve")
const amount = ref("")
const description = ref("")
let previewPayload: ResearchBudgetEntryDraft | null = null
const amendmentVisible = ref(false)
const amendmentSubmitting = ref(false)
const limitPreview = ref<ResearchOperationalLimitsPreview | null>(null)
const amendedDeadlineAt = ref<number | null>(null)
const amendedBudgetLimit = ref("")
const amendedBudgetCurrency = ref("USD")
const amendmentReason = ref("")
let limitPreviewPayload: ResearchOperationalLimitsDraft | null = null

const currentDeadlineAt = computed(() => limits.value
  ? limits.value.deadline_at ?? null
  : props.deadlineAt ?? null)
const currentBudgetLimit = computed(() => limits.value
  ? limits.value.budget.limit ?? null
  : props.budgetLimit ?? null)
const currentBudgetCurrency = computed(() => limits.value
  ? limits.value.budget.currency ?? "USD"
  : props.budgetCurrency ?? "USD")
const currentTaskRevision = computed(() => limits.value?.task_revision ?? props.taskRevision)

const kindOptions = computed(() => (["reserve", "release", "expense", "credit"] as const).map(value => ({
  label: budgetKindLabel(value),
  value,
})))
const valid = computed(() => Number(amount.value) > 0 && Boolean(description.value.trim()))
const budgetPercentage = computed(() => {
  const limit = Number(currentBudgetLimit.value || 0)
  const committed = Number(budget.value?.committed || 0)
  return limit > 0 ? Math.min(100, Math.max(0, (committed / limit) * 100)) : 0
})
const amendmentDeadlineInvalid = computed(() => Boolean(
  amendedDeadlineAt.value && amendedDeadlineAt.value <= Date.now(),
))
const amendmentChanged = computed(() => {
  const deadline = amendedDeadlineAt.value
    ? new Date(amendedDeadlineAt.value).toISOString()
    : null
  const currentDeadline = currentDeadlineAt.value
    ? new Date(currentDeadlineAt.value).toISOString()
    : null
  return deadline !== currentDeadline
    || !sameDecimal(amendedBudgetLimit.value, currentBudgetLimit.value)
    || (amendedBudgetLimit.value.trim() ? amendedBudgetCurrency.value : null)
    !== (currentBudgetLimit.value ? currentBudgetCurrency.value : null)
})
const amendmentBudgetInvalid = computed(() => {
  const proposed = amendedBudgetLimit.value.trim()
  const proposedAmount = decimalValue(proposed)
  if (proposed && (!proposedAmount || proposedAmount.lte(0)))
    return true
  if (budget.value?.entries.length) {
    if (!proposed || amendedBudgetCurrency.value !== currentBudgetCurrency.value)
      return true
  }
  const budgetChanged = !sameDecimal(proposed, currentBudgetLimit.value)
  const committed = decimalValue(budget.value?.committed)
  return Boolean(
    budgetChanged
    && proposedAmount
    && committed
    && proposedAmount.lte(committed),
  )
})
const amendmentValid = computed(() => Boolean(
  amendmentReason.value.trim()
  && !amendmentDeadlineInvalid.value
  && !amendmentBudgetInvalid.value
  && amendmentChanged.value,
))
const currencyOptions = ["USD", "CNY", "EUR", "GBP", "JPY"].map(value => ({
  label: value,
  value,
}))

function budgetKindLabel(value: ResearchBudgetEntryKind) {
  return $t(`page.research.budgetEntryKinds.${value}` as I18n.I18nKey)
}

function decimalValue(value: string | null | undefined) {
  if (!value?.trim())
    return null
  try {
    return new Big(value)
  }
  catch {
    return undefined
  }
}

function sameDecimal(left: string | null | undefined, right: string | null | undefined) {
  const leftValue = decimalValue(left)
  const rightValue = decimalValue(right)
  if (leftValue === null || rightValue === null)
    return leftValue === rightValue
  if (!leftValue || !rightValue)
    return false
  return leftValue.eq(rightValue)
}

async function loadBudget() {
  budgetLoading.value = true
  budgetError.value = false
  try {
    limits.value = await fetchResearchOperationalLimits(props.taskId)
    budget.value = limits.value.budget
  }
  catch {
    limits.value = null
    budget.value = null
    budgetError.value = true
  }
  finally {
    budgetLoading.value = false
  }
}

function payload(): ResearchBudgetEntryDraft {
  return {
    expected_task_revision: currentTaskRevision.value,
    kind: kind.value,
    amount: amount.value,
    currency: currentBudgetCurrency.value,
    description: description.value.trim(),
    idempotency_key: `budget-${nanoid()}`,
  }
}

function limitSummary(value: ResearchOperationalLimitValues) {
  const deadline = value.deadline_at
    ? new Date(value.deadline_at).toLocaleString()
    : $t("page.research.noLimit")
  const budgetText = value.budget_limit
    ? `${value.budget_limit} ${value.budget_currency || ""}`.trim()
    : $t("page.research.noLimit")
  return `${$t("page.research.deadline")} · ${deadline}; ${$t("page.research.budgetLimit")} · ${budgetText}`
}

function isDeadlineDisabled(timestamp: number) {
  return timestamp < new Date().setHours(0, 0, 0, 0)
}

function openAmendment() {
  amendedDeadlineAt.value = currentDeadlineAt.value
    ? new Date(currentDeadlineAt.value).getTime()
    : null
  amendedBudgetLimit.value = currentBudgetLimit.value || ""
  amendedBudgetCurrency.value = currentBudgetCurrency.value
  amendmentReason.value = ""
  amendmentVisible.value = true
}

function operationalLimitPayload(): ResearchOperationalLimitsDraft {
  const budgetLimit = amendedBudgetLimit.value.trim()
  return {
    expected_task_revision: currentTaskRevision.value,
    deadline_at: amendedDeadlineAt.value
      ? new Date(amendedDeadlineAt.value).toISOString()
      : null,
    budget_limit: budgetLimit || null,
    budget_currency: budgetLimit ? amendedBudgetCurrency.value : null,
    reason: amendmentReason.value.trim(),
    idempotency_key: `limits-${nanoid()}`,
  }
}

async function handleLimitPreview() {
  if (!amendmentValid.value)
    return
  amendmentSubmitting.value = true
  try {
    limitPreviewPayload = operationalLimitPayload()
    limitPreview.value = await previewResearchOperationalLimits(
      props.taskId,
      limitPreviewPayload,
    )
  }
  finally {
    amendmentSubmitting.value = false
  }
}

async function handleAmendment() {
  if (!limitPreview.value || !limitPreviewPayload)
    return
  amendmentSubmitting.value = true
  try {
    const result = await amendResearchOperationalLimits(props.taskId, {
      ...limitPreviewPayload,
      preview_digest: limitPreview.value.preview_digest,
    })
    limits.value = result.operational_limits
    budget.value = result.operational_limits.budget
    window.$message?.success($t("page.research.operationalLimitsAmended"))
    amendmentVisible.value = false
    emit("changed")
  }
  finally {
    amendmentSubmitting.value = false
  }
}

async function handlePreview() {
  if (!valid.value)
    return
  submitting.value = true
  try {
    previewPayload = payload()
    preview.value = await previewResearchBudgetEntry(props.taskId, previewPayload)
  }
  finally {
    submitting.value = false
  }
}

async function handleCreate() {
  if (!preview.value || !previewPayload)
    return
  submitting.value = true
  try {
    const result = await createResearchBudgetEntry(props.taskId, {
      ...previewPayload,
      preview_digest: preview.value.preview_digest,
    })
    budget.value = result.budget
    if (limits.value) {
      limits.value = {
        ...limits.value,
        task_revision: result.task_revision,
        budget: result.budget,
      }
    }
    window.$message?.success($t("page.research.budgetEntryRecorded"))
    entryVisible.value = false
    emit("changed")
  }
  finally {
    submitting.value = false
  }
}

function reset() {
  preview.value = null
  previewPayload = null
  kind.value = "reserve"
  amount.value = ""
  description.value = ""
}

function resetAmendment() {
  limitPreview.value = null
  limitPreviewPayload = null
  amendedDeadlineAt.value = null
  amendedBudgetLimit.value = ""
  amendedBudgetCurrency.value = "USD"
  amendmentReason.value = ""
}

watch(() => props.taskId, () => void loadBudget(), { immediate: true })
</script>

<style scoped>
.research-budget-entry,
.research-budget-preview {
  border: 1px solid rgb(226 232 240);
  border-radius: 0.75rem;
  background: rgb(248 250 252 / 75%);
  padding: 0.75rem;
}

.research-budget-modal {
  width: min(36rem, calc(100vw - 2rem));
}
</style>
