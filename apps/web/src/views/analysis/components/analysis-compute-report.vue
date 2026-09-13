<template>
  <section class="compute-report" data-testid="analysis-compute-report">
    <n-alert v-if="cancelReceipt" type="info" class="my-3" data-testid="analysis-compute-cancel-receipt">
      {{ t("page.analysis.compute.cancelReceipt", { status: t(`page.analysis.compute.states.${cancelReceipt.status}`) }) }}
    </n-alert>
    <n-alert v-if="errorMessage" type="error" class="my-3">
      {{ errorMessage }}
    </n-alert>
    <div class="flex flex-wrap items-center justify-between gap-2">
      <h3 class="aira-type-label">
        {{ t(approvalOnly ? "page.analysis.compute.approvalTitle" : "page.analysis.compute.reportTitle") }}
      </h3>
      <n-button size="small" :loading="loading" @click="loadDetail">
        {{ t("common.refresh") }}
      </n-button>
    </div>
    <template v-if="detail">
      <n-alert type="info" class="mb-4">
        {{ t(approvalOnly ? "page.analysis.compute.approvalPrivacy" : "page.analysis.compute.privateHint") }}
      </n-alert>
      <div class="mb-3 flex flex-wrap gap-2">
        <n-tag :type="detail.job.status === 'completed' ? 'success' : detail.job.status === 'failed' ? 'error' : 'info'">
          {{ t(`page.analysis.compute.states.${detail.job.status}`) }}
        </n-tag>
        <span class="aira-type-meta">{{ detail.job.language }} · {{ t("page.analysis.compute.attempt", { count: detail.job.attempt_count }) }}</span>
      </div>
      <n-alert v-if="detail.job.status === 'queued'" type="warning" class="mb-3">
        {{ t("page.analysis.compute.queuedHint") }}
      </n-alert>
      <n-alert v-if="detail.job.status === 'cancel_requested'" type="warning" class="mb-3">
        {{ t("page.analysis.compute.cancellingHint") }}
      </n-alert>
      <n-alert v-if="detail.job.error || detail.job.cancel_reason" type="error" class="mb-3">
        {{ detail.job.error || detail.job.cancel_reason }}
      </n-alert>
      <p class="aira-type-meta">
        {{ detail.run.question }}
      </p>
      <p v-if="detail.job.heartbeat_at" class="aira-type-meta">
        {{ t("page.analysis.compute.heartbeat") }}: {{ formatTime(detail.job.heartbeat_at) }}
      </p>
      <p v-if="detail.job.actual_cost !== null && detail.job.actual_cost !== undefined" class="aira-type-meta">
        {{ t("page.analysis.compute.actualCost") }}: {{ detail.job.actual_cost }} {{ detail.job.currency }}
      </p>
      <template v-if="!isTerminal">
        <analysis-compute-contract :contract="detail.contract" :mode="needsApprovalReview ? 'approval' : 'historical'" />
        <p class="aira-type-meta break-all">
          {{ t("page.analysis.compute.contractDigest") }}: {{ detail.approval.contract_digest }}
        </p>
      </template>
      <div v-if="needsApprovalReview" class="mt-4">
        <template v-if="detail.approval.can_approve">
          <n-checkbox v-model:checked="reviewed" data-testid="analysis-compute-reviewed">
            {{ t("page.analysis.compute.reviewed") }}
          </n-checkbox>
          <div class="mt-3 flex flex-wrap gap-2">
            <n-button type="primary" :disabled="!reviewed || busy" data-testid="analysis-compute-approve" @click="openDecision('approved')">
              {{ t("page.analysis.compute.approve") }}
            </n-button>
            <n-button type="error" :disabled="busy" data-testid="analysis-compute-reject" @click="openDecision('rejected')">
              {{ t("page.analysis.compute.reject") }}
            </n-button>
          </div>
        </template>
        <template v-else>
          <p class="aira-type-meta">
            {{ t("page.analysis.compute.awaitingApprover", { name: detail.contract.approver.name }) }}
          </p>
          <a v-if="!approvalOnly" :href="approvalLink" class="aira-type-meta">{{ t("page.analysis.compute.approvalLink") }}</a>
        </template>
      </div>
      <n-button v-if="!approvalOnly && canCancel" type="error" size="small" class="mt-3" :disabled="busy" data-testid="analysis-compute-cancel" @click="openDecision('cancel')">
        {{ t("page.analysis.compute.cancel") }}
      </n-button>
      <template v-if="!approvalOnly && detail.job.status === 'completed'">
        <h3 class="aira-type-label mt-4">
          {{ t("page.analysis.compute.result") }}
        </h3>
        <n-alert type="info" class="mb-3">
          {{ t("page.analysis.compute.resultHint") }}
        </n-alert>
        <pre tabindex="0" data-testid="analysis-compute-result">{{ JSON.stringify(detail.job.result, null, 2) }}</pre>
        <div v-for="output in detail.job.output_manifest" :key="output.id" class="compute-output-row">
          <div class="min-w-0">
            <div class="aira-type-label break-all">
              {{ output.asset_name || output.mount_name }}
            </div><div class="aira-type-meta break-all">
              {{ output.media_type }} · {{ output.byte_size ?? '—' }} B · {{ output.checksum_sha256 || '—' }}
            </div>
          </div>
          <n-button v-if="output.checksum_sha256" size="small" :loading="downloading === output.id" data-testid="analysis-compute-output-download" @click="downloadOutput(output.id, output.mount_name, output.media_type)">
            {{ t("common.download") }}
          </n-button>
        </div>
      </template>
      <details v-if="isTerminal" class="compute-historical-contract mt-4" data-testid="analysis-compute-historical-contract">
        <summary class="aira-type-label">
          {{ t("page.analysis.compute.historicalContract") }}
        </summary>
        <div class="mt-3">
          <analysis-compute-contract :contract="detail.contract" mode="historical" />
          <p class="aira-type-meta break-all">
            {{ t("page.analysis.compute.contractDigest") }}: {{ detail.approval.contract_digest }}
          </p>
        </div>
      </details>
      <details v-if="detail.events.length" class="mt-4">
        <summary class="aira-type-meta">
          {{ t("page.analysis.compute.events") }}
        </summary><ol class="aira-type-meta">
          <li v-for="event in detail.events" :key="event.id">
            {{ formatTime(event.created_at) }} · {{ event.kind }}
          </li>
        </ol>
      </details>
    </template>
    <n-modal v-model:show="decisionVisible" preset="card" class="aira-dialog" style="--aira-dialog-width: 38rem" :title="decisionTitle" :mask-closable="false" :closable="!busy" data-testid="analysis-compute-decision-dialog">
      <n-alert type="warning" class="mb-4">
        {{ t(decision === 'cancel' ? "page.analysis.compute.cancelHint" : "page.analysis.compute.decisionHint") }}
      </n-alert>
      <p class="aira-type-meta break-all">
        {{ t("page.analysis.compute.contractDigest") }}: {{ decisionSnapshot?.digest }}
      </p>
      <n-alert v-if="errorMessage" type="error" class="mb-3">
        {{ errorMessage }}
      </n-alert>
      <n-alert v-if="cancellationAttempt && !busy" type="warning" class="mb-3">
        {{ t("page.analysis.compute.cancelUncertain") }}
      </n-alert>
      <n-input v-model:value="reason" :disabled="busy || Boolean(cancellationAttempt)" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :placeholder="t('page.analysis.compute.reason')" :aria-label="t('page.analysis.compute.reason')" data-testid="analysis-compute-reason" />
      <template #footer>
        <div class="flex justify-end gap-2">
          <n-button :disabled="busy" @click="decisionVisible = false">
            {{ t("common.cancel") }}
          </n-button><n-button :type="decision === 'approved' ? 'primary' : 'error'" :disabled="!reason.trim()" :loading="busy" data-testid="analysis-compute-confirm-decision" @click="confirmDecision">
            {{ t("common.confirm") }}
          </n-button>
        </div>
      </template>
    </n-modal>
  </section>
</template>

<script setup lang="ts">
import type { AnalysisRun } from "@/service/api/analysis"
import type { AnalysisComputeDetail } from "@/service/api/analysis-compute"
import { cancelAnalysisCompute, decideAnalysisCompute, downloadAnalysisComputeOutput, fetchAnalysisCompute } from "@/service/api/analysis-compute"
import { downloadAs } from "@airalogy/shared/utils"
import { useI18n } from "vue-i18n"
import AnalysisComputeContract from "./analysis-compute-contract.vue"

const props = defineProps<{ runId: string, projectId: string, approvalOnly?: boolean }>()
const emit = defineEmits<{ updated: [run: AnalysisRun] }>()
const { t, locale } = useI18n()
const router = useRouter()
const route = useRoute()
const detail = ref<AnalysisComputeDetail | null>(null)
const loading = ref(false)
const busy = ref(false)
const reviewed = ref(false)
const errorMessage = ref("")
const downloading = ref("")
const decisionVisible = ref(false)
const decision = ref<"approved" | "rejected" | "cancel">("approved")
const reason = ref("")
const cancelReceipt = ref<Awaited<ReturnType<typeof cancelAnalysisCompute>> | null>(null)
const decisionSnapshot = ref<{ runId: string, digest: string, approvalRevision: number, jobRevision: number } | null>(null)
const cancellationAttempt = ref<{ runId: string, payload: Parameters<typeof cancelAnalysisCompute>[1] } | null>(null)
let sequence = 0
let timer: ReturnType<typeof setTimeout> | undefined
const canCancel = computed(() => detail.value && ["awaiting_approval", "queued", "leased", "running"].includes(detail.value.job.status))
const isTerminal = computed(() => Boolean(detail.value && ["completed", "failed", "cancelled"].includes(detail.value.job.status)))
const needsApprovalReview = computed(() => detail.value?.approval.state === "pending" && detail.value.job.status === "awaiting_approval")
const decisionTitle = computed(() => t(decision.value === "approved" ? "page.analysis.compute.approve" : decision.value === "rejected" ? "page.analysis.compute.reject" : "page.analysis.compute.cancel"))
const approvalLink = computed(() => router.resolve({ name: "project-analysis", params: { labUid: route.params.labUid, projectUid: route.params.projectUid }, query: { computeApproval: props.runId } }).href)
function formatTime(value: string) {
  return new Date(value).toLocaleString(locale.value)
}
function errorText(error: unknown) {
  const status = (error as { response?: { status?: number } })?.response?.status
  return t(status === 409 ? "page.analysis.stalePreview" : status === 403 || status === 404 ? "page.analysis.compute.accessChanged" : "page.analysis.requestError")
}
async function loadDetail() {
  const version = ++sequence
  if (timer)
    clearTimeout(timer)
  loading.value = true
  try {
    const fetched = await fetchAnalysisCompute(props.runId, props.approvalOnly)
    if (version !== sequence)
      return
    if (fetched.run.project_id !== props.projectId || fetched.run.id !== props.runId)
      throw new Error("Analysis compute scope mismatch")
    if (detail.value?.approval.contract_digest !== fetched.approval.contract_digest || detail.value?.approval.revision !== fetched.approval.revision) {
      reviewed.value = false
      decisionVisible.value = false
    }
    detail.value = fetched
    errorMessage.value = ""
    if (!props.approvalOnly)
      emit("updated", fetched.run)
    if (["awaiting_approval", "queued", "leased", "running", "cancel_requested"].includes(fetched.job.status))
      timer = setTimeout(() => void loadDetail(), 4000)
  }
  catch (error) {
    if (version === sequence) {
      detail.value = null
      reviewed.value = false
      errorMessage.value = errorText(error)
    }
  }
  finally {
    if (version === sequence)
      loading.value = false
  }
}
function openDecision(value: typeof decision.value) {
  if (!detail.value || (value === "approved" && !reviewed.value))
    return
  decisionSnapshot.value = { runId: props.runId, digest: detail.value.approval.contract_digest, approvalRevision: detail.value.approval.revision, jobRevision: detail.value.job.revision }
  decision.value = value
  reason.value = value === "cancel" && cancellationAttempt.value ? cancellationAttempt.value.payload.reason : ""
  decisionVisible.value = true
}
async function confirmDecision() {
  // A confirmed cancellation can recover its safe receipt after source access
  // has disappeared. Approval still requires readable current contract details.
  if ((!detail.value && decision.value !== "cancel") || !decisionSnapshot.value || !reason.value.trim() || busy.value)
    return
  const snapshot = decisionSnapshot.value
  const id = snapshot.runId
  const digest = snapshot.digest
  busy.value = true
  try {
    if (decision.value === "cancel") {
      const attempt = cancellationAttempt.value || { runId: id, payload: { expected_revision: snapshot.jobRevision, reason: reason.value.trim(), contract_digest: digest } }
      cancellationAttempt.value = attempt
      cancelReceipt.value = await cancelAnalysisCompute(attempt.runId, attempt.payload)
      cancellationAttempt.value = null
    }
    else {
      await decideAnalysisCompute(id, { decision: decision.value, expected_revision: snapshot.approvalRevision, contract_digest: digest, reason: reason.value.trim() })
    }
    if (id === props.runId) {
      decisionVisible.value = false
      await loadDetail()
    }
  }
  catch (error) {
    if (id === props.runId) {
      errorMessage.value = errorText(error)
      if (decision.value === "cancel" && (error as { response?: { status?: number } })?.response?.status === 409) {
        cancellationAttempt.value = null
        decisionVisible.value = false
        await loadDetail()
      }
    }
  }
  finally { busy.value = false }
}
async function downloadOutput(id: string, filename: string, mediaType: string) {
  downloading.value = id
  try {
    const blob = await downloadAnalysisComputeOutput(props.runId, id)
    downloadAs(blob, filename, mediaType)
  }
  catch (error) { errorMessage.value = errorText(error) }
  finally { downloading.value = "" }
}
watch(() => [props.runId, props.projectId, props.approvalOnly], () => {
  detail.value = null
  reviewed.value = false
  decisionVisible.value = false
  cancelReceipt.value = null
  cancellationAttempt.value = null
  void loadDetail()
}, { immediate: true })
onBeforeUnmount(() => {
  sequence += 1
  if (timer)
    clearTimeout(timer)
})
</script>

<style scoped>
.compute-report { min-width: 0; }
.compute-output-row { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: .6rem; margin-top: .75rem; padding: .75rem; border: 1px solid #e5e7eb; border-radius: .5rem; }
pre { max-width: 100%; max-height: 20rem; overflow: auto; padding: .75rem; border-radius: .5rem; background: #f7f9fc; font-size: .75rem; }
pre:focus-visible, summary:focus-visible { outline: 2px solid #0084e2; outline-offset: 2px; }
summary { cursor: pointer; }
.compute-historical-contract { padding: .75rem; border: 1px solid #e5e7eb; border-radius: .5rem; }
</style>
