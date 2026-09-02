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
      <n-button
        v-if="canManage && budgetLimit"
        size="small"
        secondary
        @click="entryVisible = true"
      >
        {{ $t("page.research.recordBudgetEntry") }}
      </n-button>
    </div>

    <div class="mt-4 space-y-4">
      <div>
        <div class="aira-type-meta">
          {{ $t("page.research.deadline") }}
        </div>
        <div class="aira-type-label mt-1">
          {{ deadlineAt ? new Date(deadlineAt).toLocaleString() : $t("page.research.noLimit") }}
        </div>
      </div>
      <div v-if="budgetLimit">
        <n-alert v-if="budgetError" type="error">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <span>{{ $t("page.research.budgetLoadError") }}</span>
            <n-button size="tiny" @click="loadBudget">
              {{ $t("common.retry") }}
            </n-button>
          </div>
        </n-alert>
        <n-spin v-else :show="budgetLoading">
          <div class="flex items-center justify-between gap-3">
            <span class="aira-type-meta">{{ $t("page.research.budgetCommitted") }}</span>
            <span class="aira-type-label">
              {{ budget?.committed || "0" }} / {{ budgetLimit }} {{ budgetCurrency }}
            </span>
          </div>
          <n-progress class="mt-2" type="line" :percentage="budgetPercentage" :show-indicator="false" />
          <div class="aira-type-meta mt-2 flex flex-wrap justify-between gap-2">
            <span>{{ $t("page.research.budgetReserved") }} · {{ budget?.reserved || "0" }}</span>
            <span>{{ $t("page.research.budgetActual") }} · {{ budget?.actual || "0" }}</span>
            <span>{{ $t("page.research.budgetRemaining") }} · {{ budget?.remaining ?? budgetLimit }}</span>
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
            <n-input-group-label>{{ budgetCurrency }}</n-input-group-label>
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
          <div>{{ $t("page.research.budgetCommitted") }} · {{ preview.projected.committed }} {{ budgetCurrency }}</div>
          <div>{{ $t("page.research.budgetRemaining") }} · {{ preview.projected.remaining }} {{ budgetCurrency }}</div>
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
</template>

<script setup lang="ts">
import type {
  ResearchBudgetEntryDraft,
  ResearchBudgetEntryKind,
  ResearchBudgetPreview,
  ResearchBudgetSnapshot,
} from "@/service/api/research-budget"
import {
  createResearchBudgetEntry,
  fetchResearchBudget,
  previewResearchBudgetEntry,
} from "@/service/api/research-budget"
import { $t } from "@airalogy/shared/locales"
import { nanoid } from "nanoid"

const props = defineProps<{
  taskId: string
  taskRevision: number
  deadlineAt?: string | null
  budgetLimit?: string | null
  budgetCurrency?: string | null
  canManage: boolean
}>()
const emit = defineEmits<{ changed: [] }>()

const budget = ref<ResearchBudgetSnapshot | null>(null)
const budgetLoading = ref(false)
const budgetError = ref(false)
const entryVisible = ref(false)
const submitting = ref(false)
const preview = ref<ResearchBudgetPreview | null>(null)
const kind = ref<ResearchBudgetEntryKind>("reserve")
const amount = ref("")
const description = ref("")
let previewPayload: ResearchBudgetEntryDraft | null = null

const kindOptions = computed(() => (["reserve", "release", "expense", "credit"] as const).map(value => ({
  label: budgetKindLabel(value),
  value,
})))
const valid = computed(() => Number(amount.value) > 0 && Boolean(description.value.trim()))
const budgetPercentage = computed(() => {
  const limit = Number(props.budgetLimit || 0)
  const committed = Number(budget.value?.committed || 0)
  return limit > 0 ? Math.min(100, Math.max(0, (committed / limit) * 100)) : 0
})

function budgetKindLabel(value: ResearchBudgetEntryKind) {
  return $t(`page.research.budgetEntryKinds.${value}` as I18n.I18nKey)
}

async function loadBudget() {
  if (!props.budgetLimit)
    return
  budgetLoading.value = true
  budgetError.value = false
  try {
    budget.value = await fetchResearchBudget(props.taskId)
  }
  catch {
    budget.value = null
    budgetError.value = true
  }
  finally {
    budgetLoading.value = false
  }
}

function payload(): ResearchBudgetEntryDraft {
  return {
    expected_task_revision: props.taskRevision,
    kind: kind.value,
    amount: amount.value,
    currency: props.budgetCurrency || "USD",
    description: description.value.trim(),
    idempotency_key: `budget-${nanoid()}`,
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
