<template>
  <div class="research-service-job">
    <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
      <div class="min-w-0">
        <div class="flex flex-wrap items-center gap-2">
          <span class="aira-type-label">
            {{ job.provider_snapshot.name }} · {{ job.offering_snapshot.name }}
          </span>
          <n-tag size="small" round :type="statusType">{{ statusLabel }}</n-tag>
          <n-tag size="small" round :type="riskType">{{ job.risk }}</n-tag>
        </div>
        <div class="aira-type-meta mt-1">
          v{{ job.service_version }} · r{{ job.service_offering_revision }}
          <template v-if="job.external_order_ref"> · {{ $t("page.research.externalOrderRef") }} {{ job.external_order_ref }}</template>
        </div>
        <div v-if="job.quote" class="aira-type-meta mt-1">
          {{ $t("page.research.approvedQuote") }} · {{ job.quote.amount }} {{ job.quote.currency }}
          <template v-if="job.actual_amount"> · {{ $t("page.research.actualCost") }} {{ job.actual_amount }} {{ job.quote.currency }}</template>
        </div>
        <div v-if="job.expected_completion_at" class="aira-type-meta mt-1">
          {{ $t("page.research.expectedCompletion") }} · {{ formatDate(job.expected_completion_at) }}
        </div>
      </div>
      <div v-if="canManage" class="flex shrink-0 flex-wrap gap-2">
        <n-button v-if="job.status === 'awaiting_quote'" size="small" type="primary" @click="open('quote')">
          {{ $t("page.research.recordQuote") }}
        </n-button>
        <template v-if="job.status === 'ordered' || job.status === 'in_fulfillment'">
          <n-button size="small" secondary @click="open('progress')">{{ $t("page.research.updateServiceProgress") }}</n-button>
          <n-button size="small" secondary @click="open('custody')">{{ $t("page.research.recordCustody") }}</n-button>
          <n-button size="small" type="primary" @click="open('result')">{{ $t("page.research.receiveServiceResult") }}</n-button>
        </template>
      </div>
    </div>
    <n-alert v-if="job.error" type="error" class="mt-3">{{ job.error }}</n-alert>
    <n-collapse class="mt-3">
      <n-collapse-item :title="$t('page.research.serviceRequestPayload')" name="request">
        <pre>{{ JSON.stringify(job.request_payload, null, 2) }}</pre>
      </n-collapse-item>
      <n-collapse-item v-if="job.custody_events.length" :title="$t('page.research.sampleCustodyHistory')" name="custody">
        <ol class="mb-0 pl-5 space-y-2">
          <li v-for="event in job.custody_events" :key="event.id" class="aira-type-meta">
            {{ custodyKindLabel(event.kind) }} · {{ event.from_party }} → {{ event.to_party }} · {{ formatDate(event.occurred_at) }}
            <span v-if="event.tracking_ref"> · {{ event.tracking_ref }}</span>
          </li>
        </ol>
      </n-collapse-item>
      <n-collapse-item v-if="Object.keys(job.result || {}).length" :title="$t('page.research.serviceResult')" name="result">
        <pre>{{ JSON.stringify(job.result, null, 2) }}</pre>
        <div v-if="job.result_assets.length" class="mt-2 flex flex-wrap gap-2">
          <n-tag v-for="asset in job.result_assets" :key="asset.data_asset_version_id" size="small">
            {{ asset.name }} · v{{ asset.version }}
          </n-tag>
        </div>
      </n-collapse-item>
    </n-collapse>
  </div>

  <n-modal
    style="--aira-dialog-width: 48rem"
    v-model:show="visible"
    preset="card"
    class="aira-dialog research-service-operation-modal"
    :title="modalTitle"
    :mask-closable="false"
    @after-leave="reset"
  >
    <template v-if="!preview">
      <n-alert type="warning" class="mb-4">{{ operationHint }}</n-alert>
      <n-form label-placement="top">
        <template v-if="mode === 'quote'">
          <div class="grid grid-cols-1 gap-x-4 sm:grid-cols-2">
            <n-form-item :label="$t('page.research.amount')" required><n-input v-model:value="quote.amount" inputmode="decimal" /></n-form-item>
            <n-form-item :label="$t('page.research.currency')" required><n-input v-model:value="quote.currency" maxlength="3" /></n-form-item>
          </div>
          <n-form-item :label="$t('page.research.providerQuoteRef')"><n-input v-model:value="quote.provider_quote_ref" /></n-form-item>
          <n-form-item :label="$t('page.research.quoteValidUntil')"><n-date-picker v-model:value="quoteValidUntil" type="datetime" clearable class="w-full" /></n-form-item>
          <n-form-item :label="$t('page.research.serviceTerms')"><n-input v-model:value="quote.terms" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" /></n-form-item>
        </template>
        <template v-else-if="mode === 'progress'">
          <n-form-item :label="$t('page.research.serviceStatus')" required><n-select v-model:value="progress.status" :options="progressOptions" /></n-form-item>
          <n-form-item :label="$t('page.research.externalOrderRef')"><n-input v-model:value="progress.external_order_ref" /></n-form-item>
          <n-form-item :label="$t('page.research.providerStatus')"><n-input v-model:value="progress.provider_status" /></n-form-item>
          <n-form-item v-if="progress.status === 'in_fulfillment'" :label="$t('page.research.expectedCompletion')"><n-date-picker v-model:value="expectedCompletion" type="datetime" clearable class="w-full" /></n-form-item>
          <n-form-item v-else :label="$t('page.research.failureReason')" required><n-input v-model:value="progress.reason" type="textarea" /></n-form-item>
        </template>
        <template v-else-if="mode === 'custody'">
          <n-form-item :label="$t('page.research.custodyKind')" required><n-select v-model:value="custody.kind" :options="custodyOptions" /></n-form-item>
          <n-form-item :label="$t('page.research.resource')" required>
            <n-select v-model:value="custody.resource_id" :options="resourceOptions" :loading="loadingOptions" filterable @update:value="loadResourceDetail" />
          </n-form-item>
          <n-form-item v-if="containerOptions.length" :label="$t('page.research.inventoryContainer')"><n-select v-model:value="custody.container_id" :options="containerOptions" clearable /></n-form-item>
          <div class="grid grid-cols-1 gap-x-4 sm:grid-cols-2">
            <n-form-item :label="$t('page.research.fromParty')" required><n-input v-model:value="custody.from_party" /></n-form-item>
            <n-form-item :label="$t('page.research.toParty')" required><n-input v-model:value="custody.to_party" /></n-form-item>
          </div>
          <n-form-item :label="$t('page.research.occurredAt')" required><n-date-picker v-model:value="occurredAt" type="datetime" class="w-full" /></n-form-item>
          <div class="grid grid-cols-1 gap-x-4 sm:grid-cols-2">
            <n-form-item :label="$t('page.research.carrier')"><n-input v-model:value="custody.carrier" /></n-form-item>
            <n-form-item :label="$t('page.research.trackingRef')"><n-input v-model:value="custody.tracking_ref" /></n-form-item>
          </div>
          <n-form-item :label="$t('page.research.location')"><n-input v-model:value="custody.location" /></n-form-item>
          <n-form-item :label="$t('page.research.notes')"><n-input v-model:value="custody.notes" type="textarea" /></n-form-item>
        </template>
        <template v-else>
          <n-form-item
            :label="$t('page.research.serviceResultPayload')"
            required
            :validation-status="resultValid ? undefined : 'error'"
            :feedback="resultValid ? $t('page.research.serviceResultSchemaHint') : $t('page.research.invalidJsonObject')"
          >
            <n-input v-model:value="resultText" type="textarea" :autosize="{ minRows: 5, maxRows: 14 }" class="font-mono" />
          </n-form-item>
          <n-collapse>
            <n-collapse-item :title="$t('page.research.pinnedContract')" name="result-contract"><pre>{{ JSON.stringify(job.result_schema, null, 2) }}</pre></n-collapse-item>
          </n-collapse>
          <n-form-item :label="$t('page.research.resultDataAssets')">
            <n-select v-model:value="resultAssets" :options="dataAssetOptions" :loading="loadingOptions" multiple clearable filterable />
          </n-form-item>
          <n-form-item :label="$t('page.research.actualCost')"><n-input v-model:value="actualAmount" inputmode="decimal" :placeholder="job.quote?.amount" /></n-form-item>
        </template>
      </n-form>
    </template>
    <template v-else>
      <n-alert type="info">{{ $t("page.research.serviceOperationPreviewHint") }}</n-alert>
      <section class="service-operation-preview mt-4">
        <div class="aira-type-eyebrow">{{ $t("page.research.effects") }}</div>
        <ul class="aira-type-body aira-text-secondary mb-0 mt-2 pl-5"><li v-for="effect in preview.effects" :key="effect">{{ effect }}</li></ul>
        <pre class="mt-3">{{ JSON.stringify(preview.command, null, 2) }}</pre>
      </section>
    </template>
    <template #footer>
      <div class="flex justify-end gap-2">
        <n-button @click="preview ? preview = null : visible = false">{{ preview ? $t("page.research.backToEdit") : $t("common.cancel") }}</n-button>
        <n-button v-if="!preview" type="primary" :disabled="!valid" :loading="submitting" @click="handlePreview">{{ $t("page.research.previewAction") }}</n-button>
        <n-button v-else type="primary" :loading="submitting" @click="handleConfirm">{{ $t("page.research.confirmAction") }}</n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import type { DataAsset } from "@/service/api/research-assets"
import type { ServiceCustodyDraft, ServiceOperationPreview, ServiceProgressDraft, ServiceQuoteDraft, ServiceResultDraft } from "@/service/api/research-service-jobs"
import type { ResearchServiceJob } from "@/service/api/research-tasks"
import type { ResourceDetail, ResourceItem } from "@/service/api/resources"
import type { TagProps } from "naive-ui"
import { fetchResearchAssets } from "@/service/api/research-assets"
import {
  previewServiceCustody,
  previewServiceProgress,
  previewServiceQuote,
  previewServiceResult,
  recordServiceCustody,
  recordServiceProgress,
  recordServiceQuote,
  recordServiceResult,
} from "@/service/api/research-service-jobs"
import { fetchResource, fetchResources } from "@/service/api/resources"
import { $t } from "@airalogy/shared/locales"

type Mode = "quote" | "progress" | "custody" | "result"
const props = defineProps<{ job: ResearchServiceJob, taskId: string, labId: string, canManage: boolean }>()
const emit = defineEmits<{ changed: [] }>()
const visible = ref(false)
const mode = ref<Mode>("quote")
const preview = ref<ServiceOperationPreview | null>(null)
const previewPayload = ref<ServiceQuoteDraft | ServiceProgressDraft | ServiceCustodyDraft | ServiceResultDraft | null>(null)
const submitting = ref(false)
const loadingOptions = ref(false)
const quoteValidUntil = ref<number | null>(null)
const expectedCompletion = ref<number | null>(null)
const occurredAt = ref(Date.now())
const resultText = ref("{}")
const actualAmount = ref("")
const resultAssets = ref<string[]>([])
const resources = ref<ResourceItem[]>([])
const resourceDetail = ref<ResourceDetail | null>(null)
const dataAssets = ref<DataAsset[]>([])
const quote = reactive({ amount: "", currency: "USD", provider_quote_ref: "", terms: "" })
const progress = reactive({ status: "in_fulfillment" as ServiceProgressDraft["status"], external_order_ref: "", provider_status: "", reason: "" })
const custody = reactive({ kind: "prepared" as ServiceCustodyDraft["kind"], resource_id: "", container_id: "", from_party: "", to_party: "", location: "", carrier: "", tracking_ref: "", notes: "" })

const statusLabel = computed(() => $t(`page.research.serviceJobStatus.${props.job.status}` as I18n.I18nKey))
const statusType = computed<TagProps["type"]>(() => props.job.status === "completed" ? "success" : ["failed", "cancelled"].includes(props.job.status) ? "error" : ["awaiting_quote", "awaiting_approval"].includes(props.job.status) ? "warning" : "info")
const riskType = computed<TagProps["type"]>(() => props.job.risk === "high" ? "error" : props.job.risk === "medium" ? "warning" : "info")
const modalTitle = computed(() => $t(`page.research.serviceOperation.${mode.value}` as I18n.I18nKey))
const operationHint = computed(() => $t(`page.research.serviceOperationHint.${mode.value}` as I18n.I18nKey))
const progressOptions = computed(() => [
  { label: $t("page.research.serviceJobStatus.in_fulfillment"), value: "in_fulfillment" },
  { label: $t("page.research.serviceJobStatus.failed"), value: "failed" },
])
const custodyKinds: ServiceCustodyDraft["kind"][] = ["prepared", "released_to_carrier", "received_by_provider", "returned_to_lab", "disposed_by_provider"]
const custodyOptions = computed(() => custodyKinds.map(value => ({ label: custodyKindLabel(value), value })))
const resourceOptions = computed(() => resources.value.map(item => ({ label: `${item.name} · ${item.code}`, value: item.id })))
const containerOptions = computed(() => ((resourceDetail.value?.containers || []) as Array<{ id: string, code: string, status: string }>).filter(item => item.status === "active").map(item => ({ label: item.code, value: item.id })))
const dataAssetOptions = computed(() => dataAssets.value.flatMap(asset => asset.versions.map(version => ({ label: `${asset.name} · v${version.version}`, value: version.id }))))
const parsedResult = computed(() => {
  try {
    const value = JSON.parse(resultText.value || "{}")
    return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : null
  }
  catch { return null }
})
const resultValid = computed(() => parsedResult.value !== null)
const valid = computed(() => {
  if (mode.value === "quote")
    return Number(quote.amount) >= 0 && quote.currency.trim().length === 3
  if (mode.value === "progress")
    return progress.status === "in_fulfillment" || Boolean(progress.reason.trim())
  if (mode.value === "custody")
    return Boolean(custody.resource_id && custody.from_party.trim() && custody.to_party.trim() && occurredAt.value)
  return resultValid.value && (!actualAmount.value || Number(actualAmount.value) >= 0)
})

function custodyKindLabel(value: ServiceCustodyDraft["kind"]) {
  return $t(`page.research.custodyKinds.${value}` as I18n.I18nKey)
}

function formatDate(value: string) {
  return new Date(value).toLocaleString()
}

async function loadResourceDetail(resourceId: string) {
  custody.container_id = ""
  resourceDetail.value = resourceId ? await fetchResource(props.labId, resourceId) : null
}

async function open(value: Mode) {
  mode.value = value
  visible.value = true
  progress.external_order_ref = props.job.external_order_ref || ""
  progress.provider_status = props.job.provider_status || ""
  actualAmount.value = props.job.quote?.amount || ""
  loadingOptions.value = true
  try {
    if (value === "custody") {
      const response = await fetchResources(props.labId, { status: "active", page: 1, page_size: 200 })
      resources.value = response.items
    }
    if (value === "result") {
      const bundle = await fetchResearchAssets(props.taskId)
      dataAssets.value = bundle.data_assets
    }
  }
  finally {
    loadingOptions.value = false
  }
}

function payload() {
  if (mode.value === "quote") {
    return {
      expected_revision: props.job.revision,
      amount: quote.amount,
      currency: quote.currency.toUpperCase(),
      provider_quote_ref: quote.provider_quote_ref,
      valid_until: quoteValidUntil.value ? new Date(quoteValidUntil.value).toISOString() : null,
      terms: quote.terms,
    } satisfies ServiceQuoteDraft
  }
  if (mode.value === "progress") {
    return {
      expected_revision: props.job.revision,
      status: progress.status,
      external_order_ref: progress.external_order_ref,
      provider_status: progress.provider_status,
      expected_completion_at: expectedCompletion.value ? new Date(expectedCompletion.value).toISOString() : null,
      reason: progress.reason,
    } satisfies ServiceProgressDraft
  }
  if (mode.value === "custody") {
    return {
      expected_revision: props.job.revision,
      kind: custody.kind,
      resource_id: custody.resource_id,
      container_id: custody.container_id || null,
      from_party: custody.from_party,
      to_party: custody.to_party,
      location: custody.location,
      carrier: custody.carrier,
      tracking_ref: custody.tracking_ref,
      notes: custody.notes,
      condition: {},
      occurred_at: new Date(occurredAt.value).toISOString(),
    } satisfies ServiceCustodyDraft
  }
  return {
    expected_revision: props.job.revision,
    result: parsedResult.value || {},
    data_asset_version_ids: resultAssets.value,
    actual_amount: actualAmount.value || null,
  } satisfies ServiceResultDraft
}

async function handlePreview() {
  if (!valid.value)
    return
  submitting.value = true
  try {
    previewPayload.value = payload()
    if (mode.value === "quote")
      preview.value = await previewServiceQuote(props.job.id, previewPayload.value as ServiceQuoteDraft)
    else if (mode.value === "progress")
      preview.value = await previewServiceProgress(props.job.id, previewPayload.value as ServiceProgressDraft)
    else if (mode.value === "custody")
      preview.value = await previewServiceCustody(props.job.id, previewPayload.value as ServiceCustodyDraft)
    else
      preview.value = await previewServiceResult(props.job.id, previewPayload.value as ServiceResultDraft)
  }
  finally {
    submitting.value = false
  }
}

async function handleConfirm() {
  if (!preview.value || !previewPayload.value)
    return
  submitting.value = true
  try {
    const confirmed = { ...previewPayload.value, preview_digest: preview.value.preview_digest }
    if (mode.value === "quote")
      await recordServiceQuote(props.job.id, confirmed as ServiceQuoteDraft & { preview_digest: string })
    else if (mode.value === "progress")
      await recordServiceProgress(props.job.id, confirmed as ServiceProgressDraft & { preview_digest: string })
    else if (mode.value === "custody")
      await recordServiceCustody(props.job.id, confirmed as ServiceCustodyDraft & { preview_digest: string })
    else
      await recordServiceResult(props.job.id, confirmed as ServiceResultDraft & { preview_digest: string })
    window.$message?.success($t("page.research.serviceOperationSaved"))
    visible.value = false
    emit("changed")
  }
  finally {
    submitting.value = false
  }
}

function reset() {
  preview.value = null
  previewPayload.value = null
  quote.amount = ""
  quote.currency = "USD"
  quote.provider_quote_ref = ""
  quote.terms = ""
  progress.status = "in_fulfillment"
  progress.reason = ""
  custody.kind = "prepared"
  custody.resource_id = ""
  custody.container_id = ""
  custody.from_party = ""
  custody.to_party = ""
  custody.location = ""
  custody.carrier = ""
  custody.tracking_ref = ""
  custody.notes = ""
  quoteValidUntil.value = null
  expectedCompletion.value = null
  occurredAt.value = Date.now()
  resultText.value = "{}"
  resultAssets.value = []
  actualAmount.value = ""
  resources.value = []
  resourceDetail.value = null
  dataAssets.value = []
}
</script>

<style scoped>
.research-service-job { border: 1px solid rgb(226 232 240); border-radius: 0.875rem; background: rgb(248 250 252); padding: 0.875rem; }

.service-operation-preview { border: 1px solid rgb(226 232 240); border-radius: 1rem; padding: 1rem; }
pre { overflow: auto; max-height: 20rem; border-radius: 0.75rem; background: rgb(241 245 249); padding: 0.75rem; font-size: 0.75rem; }
</style>
