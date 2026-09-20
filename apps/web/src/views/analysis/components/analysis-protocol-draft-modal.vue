<template>
  <n-modal :show="show" preset="card" class="aira-dialog draft-dialog" style="--aira-dialog-width: 64rem" :title="t('page.analysisProtocolDraft.title')" :mask-closable="false" :closable="!busy && !uncertain" :close-on-esc="!busy && !uncertain" data-testid="analysis-protocol-draft-dialog" @update:show="close">
    <n-alert v-if="error" type="error" class="mb-3" data-testid="analysis-protocol-draft-error">
      {{ error }}
    </n-alert>
    <n-alert v-if="uncertain" type="warning" class="mb-3">
      {{ t('page.workflowDefinitions.confirmationUncertain') }}
      <n-button v-if="draft && !preview" size="small" :disabled="busy" @click="reloadDraft">
        {{ t('page.analysisProtocolDraft.reload') }}
      </n-button>
    </n-alert>
    <n-alert v-if="notice" type="success" class="mb-3" data-testid="analysis-protocol-draft-notice">
      {{ notice }}
    </n-alert>
    <n-alert v-if="!supported" type="info" data-testid="analysis-protocol-draft-unsupported">
      {{ t('page.analysisProtocolDraft.computeUnsupported') }}
    </n-alert>
    <n-spin v-else :show="loading">
      <p class="aira-type-meta mt-0">
        {{ t('page.analysisProtocolDraft.boundary') }}
      </p>
      <p class="draft-break">
        <strong>{{ method?.title }}</strong> · <code>{{ method?.digest }}</code>
      </p>
      <div class="draft-controls">
        <n-select :value="draft?.id ?? null" :options="draftOptions" :placeholder="t('page.analysisProtocolDraft.history')" :disabled="busy || uncertain || !!preview || loading" data-testid="analysis-protocol-draft-history" @update:value="openDraft" />
        <n-button :disabled="locked" data-testid="analysis-protocol-draft-new" @click="newDraft()">
          {{ t('page.analysisProtocolDraft.newDraft') }}
        </n-button>
        <n-button v-if="draft" :disabled="locked" data-testid="analysis-protocol-draft-reload" @click="reloadDraft">
          {{ t('page.analysisProtocolDraft.reload') }}
        </n-button>
      </div>
      <section v-if="destination" class="draft-box" data-testid="analysis-protocol-draft-destination">
        <strong>{{ t('page.analysisProtocolDraft.destination') }}: {{ destination.name }}</strong>
        <p class="aira-type-meta mb-0">
          {{ t(destination.visibility === 'public' ? 'page.analysisProtocolDraft.publicScope' : 'page.analysisProtocolDraft.privateScope') }}
        </p>
      </section>
      <template v-if="Object.keys(files).length">
        <div v-if="draft" class="draft-controls mt-3">
          <n-tag data-testid="analysis-protocol-draft-state">
            {{ t(`page.analysisProtocolDraft.states.${draft.state}`) }}
          </n-tag>
          <n-select :value="viewedRevision?.revision" :options="revisionOptions" :disabled="locked" data-testid="analysis-protocol-draft-revision" @update:value="openRevision" />
        </div>
        <n-alert v-if="historical" type="info" class="mt-3">
          {{ t('page.analysisProtocolDraft.historical') }}
        </n-alert>
        <n-alert v-if="dirty && draft?.state === 'reviewed'" type="warning" class="mt-3">
          {{ t('page.analysisProtocolDraft.reviewInvalidated') }}
        </n-alert>
        <n-alert v-if="draft?.applied" type="success" class="mt-3" data-testid="analysis-protocol-draft-applied">
          {{ t('page.analysisProtocolDraft.applied', { version: draft.applied.version }) }}
          <div class="mt-2 flex flex-wrap gap-2">
            <n-button tag="a" :href="appliedHref" target="_blank" rel="noopener noreferrer" size="small" data-testid="analysis-protocol-draft-open-protocol">
              {{ t('page.analysisProtocolDraft.openProtocol') }}
            </n-button>
            <n-button :disabled="locked" size="small" data-testid="analysis-protocol-draft-next-version" @click="newDraft(draft.applied.protocol_id)">
              {{ t('page.analysisProtocolDraft.nextVersion') }}
            </n-button>
          </div>
        </n-alert>
        <n-alert v-if="template?.target_protocol_id && !draft" type="warning" class="mt-3">
          {{ t('page.analysisProtocolDraft.increaseVersion') }}
        </n-alert>
        <n-tabs v-model:value="activeFile" type="line" class="mt-3" data-testid="analysis-protocol-draft-files">
          <n-tab-pane v-for="path in Object.keys(files)" :key="path" :name="path" :tab="path" display-directive="if">
            <template v-if="path === 'protocol.aimd'">
              <aimd-editor :model-value="files[path]" :readonly="!canEdit" :min-height="240" :show-top-bar="false" :show-toolbar="canEdit" :show-aimd-toolbar="canEdit" :show-md-toolbar="canEdit" data-testid="analysis-protocol-draft-aimd" @update:model-value="value => editFile(path, value)" />
              <n-collapse class="mt-3">
                <n-collapse-item :title="t('page.analysisProtocolDraft.renderPreview')" name="render">
                  <aimd-markdown-preview :content="files[path]" body-class="markdown-body" mode="preview" />
                </n-collapse-item>
              </n-collapse>
            </template>
            <n-input v-else-if="path === 'protocol.toml'" :value="files[path]" :readonly="!canEdit" type="textarea" :autosize="{ minRows: 10, maxRows: 24 }" class="draft-code" :aria-label="path" data-testid="analysis-protocol-draft-toml" @update:value="value => editFile(path, value)" />
            <template v-else>
              <p class="aira-type-meta">
                {{ t('page.analysisProtocolDraft.manifestReadOnly') }}
              </p>
              <pre class="draft-code draft-box" tabindex="0" data-testid="analysis-protocol-draft-manifest">{{ files[path] }}</pre>
            </template>
          </n-tab-pane>
        </n-tabs>
        <n-form-item class="mt-3" :label="t('page.analysisProtocolDraft.reason')" required label-placement="top">
          <n-input v-model:value="reason" :readonly="!canEdit" type="textarea" :autosize="{ minRows: 2, maxRows: 5 }" :maxlength="4000" data-testid="analysis-protocol-draft-reason" />
        </n-form-item>
        <div v-if="viewedRevision" class="draft-box draft-break aira-type-meta" data-testid="analysis-protocol-draft-seal">
          <p>{{ t('page.analysisProtocolDraft.packageDigest') }}: <code>{{ viewedRevision.package_digest }}</code></p>
          <p>{{ t('page.analysisProtocolDraft.manifestDigest') }}: <code>{{ viewedRevision.manifest_digest }}</code></p>
          <p>{{ t('page.analysisProtocolDraft.revisionAuthor') }}: {{ viewedRevision.created_by_user_id }} · {{ viewedRevision.created_at }}</p>
          <p v-if="dirty">
            {{ t('page.analysisProtocolDraft.unsavedSeal') }}
          </p>
        </div>
        <section v-if="preview" class="draft-box mt-3" data-testid="analysis-protocol-draft-preview">
          <h3 class="aira-type-card-title mt-0">
            {{ t(previewMode === 'publish' ? 'page.analysisProtocolDraft.publishPreview' : 'page.analysisProtocolDraft.savePreview') }}
          </h3>
          <p class="draft-break">
            {{ t('page.analysisProtocolDraft.packageDigest') }}: <code>{{ preview.package_digest }}</code>
          </p>
          <p class="draft-break">
            {{ t('page.analysisProtocolDraft.manifestDigest') }}: <code>{{ preview.manifest_digest }}</code>
          </p>
          <ul class="draft-file-manifest">
            <li v-for="file in preview.files_manifest" :key="file.path">
              <strong>{{ file.path }}</strong> · {{ file.size_bytes }} B<br><code>{{ file.sha256 }}</code>
            </li>
          </ul>
          <p class="aira-type-meta">
            {{ t('page.analysisProtocolDraft.expires', { time: preview.expires_at }) }}
          </p>
          <n-checkbox v-model:checked="acknowledged" :disabled="busy || uncertain" data-testid="analysis-protocol-draft-acknowledge">
            {{ t('page.analysisProtocolDraft.disclosure') }}
          </n-checkbox>
        </section>
        <section v-if="draft && !historical && !preview && !draft.applied && draft.state === 'draft' && draft.permissions.can_review" class="draft-box mt-3" data-testid="analysis-protocol-draft-review">
          <h3 class="aira-type-card-title mt-0">
            {{ t('page.analysisProtocolDraft.reviewTitle') }}
          </h3>
          <p>{{ t('page.analysisProtocolDraft.reviewHint') }}</p>
          <n-input v-model:value="reviewNote" type="textarea" :disabled="busy || uncertain || dirty" :placeholder="t('page.analysisProtocolDraft.reviewNote')" :aria-label="t('page.analysisProtocolDraft.reviewNote')" :autosize="{ minRows: 2, maxRows: 5 }" :maxlength="4000" data-testid="analysis-protocol-draft-review-note" />
          <n-checkbox v-model:checked="reviewAcknowledged" class="mt-3" :disabled="busy || uncertain || dirty" data-testid="analysis-protocol-draft-review-acknowledge">
            {{ t('page.analysisProtocolDraft.reviewDisclosure') }}
          </n-checkbox>
          <div class="mt-3 flex flex-wrap gap-2">
            <n-button :disabled="!canReview" type="primary" data-testid="analysis-protocol-draft-approve" @click="review('reviewed')">
              {{ t('page.analysisProtocolDraft.approve') }}
            </n-button>
            <n-button :disabled="!canReview" data-testid="analysis-protocol-draft-reject" @click="review('rejected')">
              {{ t('page.analysisProtocolDraft.reject') }}
            </n-button>
          </div>
        </section>
        <n-collapse v-if="draft?.reviews.length" class="mt-3">
          <n-collapse-item :title="t('page.analysisProtocolDraft.reviews')" name="reviews">
            <article v-for="item in draft.reviews" :key="item.id" class="draft-box draft-break">
              <strong>{{ t('page.workflowDefinitions.revision', { number: item.revision }) }} · {{ t(`page.analysisProtocolDraft.states.${item.decision}`) }}</strong>
              <p>{{ item.note }}</p><p class="aira-type-meta">
                {{ item.reviewed_by_user_id }} · {{ item.created_at }}
              </p>
              <code>{{ item.package_digest }}</code>
            </article>
          </n-collapse-item>
        </n-collapse>
      </template>
    </n-spin>
    <template #footer>
      <div class="flex flex-wrap justify-end gap-2">
        <n-button :disabled="busy || uncertain" @click="close">
          {{ t('common.close') }}
        </n-button>
        <n-button v-if="preview" :disabled="busy || uncertain" data-testid="analysis-protocol-draft-back" @click="clearPreview">
          {{ t('page.workflowDefinitions.backToEdit') }}
        </n-button>
        <n-button v-if="preview" type="primary" :loading="busy" :disabled="!acknowledged" data-testid="analysis-protocol-draft-confirm" @click="confirmPreview">
          {{ t(previewMode === 'publish' ? 'page.analysisProtocolDraft.confirmPublish' : 'page.analysisProtocolDraft.confirmSave') }}
        </n-button>
        <template v-else>
          <n-button v-if="canEdit" :disabled="!reason.trim() || !dirty || loading" :loading="busy" type="primary" data-testid="analysis-protocol-draft-preview-save" @click="previewSave">
            {{ t('page.analysisProtocolDraft.previewSave') }}
          </n-button>
          <n-button v-if="draft?.permissions.can_publish && draft.state === 'reviewed' && !historical" :disabled="dirty || locked" type="primary" data-testid="analysis-protocol-draft-preview-publish" @click="previewPublish">
            {{ t('page.analysisProtocolDraft.previewPublish') }}
          </n-button>
        </template>
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import type { AnalysisProtocolDestination, AnalysisProtocolDraft, AnalysisProtocolDraftRequest, AnalysisProtocolDraftSummary, AnalysisProtocolPreview, AnalysisProtocolRevision, AnalysisProtocolRevisionRequest, AnalysisProtocolTemplate } from "@/service/api/analysis-protocol-drafts"
import type { WorkflowAnalysisPublication } from "@/service/api/workflow-analysis-methods"
import { analysisProtocolDraftFingerprint, analysisProtocolPublishRequest, analysisProtocolReviewRequest, confirmAnalysisProtocolDraft, confirmAnalysisProtocolRevision, editAnalysisProtocolFile, fetchAnalysisProtocolDraft, fetchAnalysisProtocolDrafts, fetchAnalysisProtocolRevision, fetchAnalysisProtocolTemplate, previewAnalysisProtocolDraft, previewAnalysisProtocolPublish, previewAnalysisProtocolRevision, publishAnalysisProtocolDraft, reviewAnalysisProtocolDraft, supportsAnalysisProtocolDraft } from "@/service/api/analysis-protocol-drafts"
import { createWorkflowId } from "@/utils/workflow-editor"
import { AimdEditor } from "@airalogy/aimd-editor/vue"
import { AimdMarkdownPreview } from "@airalogy/aimd-renderer/vue"
import { useDialog } from "naive-ui"
import { computed, onBeforeUnmount, ref, watch } from "vue"
import { useI18n } from "vue-i18n"
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRouter } from "vue-router"

const props = defineProps<{ show: boolean, method: WorkflowAnalysisPublication | null }>()
const emit = defineEmits<{ "update:show": [value: boolean] }>()
const { t } = useI18n()
const router = useRouter()
const dialog = useDialog()
const supported = computed(() => supportsAnalysisProtocolDraft(props.method))
const loading = ref(false)
const busy = ref(false)
const uncertain = ref(false)
const error = ref("")
const notice = ref("")
const items = ref<AnalysisProtocolDraftSummary[]>([])
const template = ref<AnalysisProtocolTemplate | null>(null)
const draft = ref<AnalysisProtocolDraft | null>(null)
const viewedRevision = ref<AnalysisProtocolRevision | null>(null)
const files = ref<Record<string, string>>({})
const reason = ref("")
const baseline = ref("")
const activeFile = ref("protocol.toml")
const preview = ref<AnalysisProtocolPreview | null>(null)
const previewMode = ref<"save" | "publish">("save")
const saveRequest = ref<AnalysisProtocolDraftRequest | AnalysisProtocolRevisionRequest | null>(null)
const publishRequest = ref<ReturnType<typeof analysisProtocolPublishRequest> | null>(null)
const key = ref("")
const acknowledged = ref(false)
const reviewAcknowledged = ref(false)
const reviewNote = ref("")
let sequence = 0
const historical = computed(() => !!draft.value && viewedRevision.value?.revision !== draft.value.revision)
const dirty = computed(() => !!baseline.value && baseline.value !== analysisProtocolDraftFingerprint(files.value, reason.value))
const locked = computed(() => busy.value || uncertain.value || loading.value || !!preview.value)
const canEdit = computed(() => supported.value && !locked.value && !historical.value && (draft.value ? draft.value.state !== "applied" && draft.value.permissions.can_edit : !!template.value?.permissions.can_create))
const canReview = computed(() => !!draft.value?.permissions.can_review && draft.value.state === "draft" && !dirty.value && !locked.value && !historical.value && reviewAcknowledged.value && !!reviewNote.value.trim())
const destination = computed<AnalysisProtocolDestination | null>(() => preview.value?.destination ?? draft.value?.destination ?? template.value?.destination ?? null)
const draftOptions = computed(() => items.value.map(item => ({ value: item.id, label: `${item.name || item.id} · ${t(`page.analysisProtocolDraft.states.${item.state}`)} · r${item.revision}` })))
const revisionOptions = computed(() => (draft.value?.revisions ?? []).map(item => ({ value: item.revision, label: t("page.workflowDefinitions.revision", { number: item.revision }) })))
const appliedHref = computed(() => draft.value?.applied ? router.resolve({ name: "protocol-detail", params: { labUid: draft.value.applied.lab_uid, projectUid: draft.value.applied.project_uid, protocolUid: draft.value.applied.protocol_uid } }).href : undefined)

function errorText(cause: unknown) {
  const detail = (cause as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (typeof detail === "string")
    return detail
  if (Array.isArray(detail))
    return detail.map(item => typeof item?.msg === "string" ? `${item.loc?.join(".") ?? ""}: ${item.msg}` : "").filter(Boolean).join("; ") || t("page.workflowDefinitions.requestFailed")
  return t("page.workflowDefinitions.requestFailed")
}
function isUncertain(cause: unknown) {
  const status = (cause as { response?: { status?: number } })?.response?.status
  return !status || status >= 500 || status === 408
}
function clearPreview() {
  preview.value = null
  saveRequest.value = null
  publishRequest.value = null
  acknowledged.value = false
}
function setFiles(value: Record<string, string>, changeReason: string) {
  files.value = { ...value }
  reason.value = changeReason
  baseline.value = analysisProtocolDraftFingerprint(files.value, reason.value)
  activeFile.value = "protocol.toml"
  reviewAcknowledged.value = false
  reviewNote.value = ""
}
function acceptDraft(value: AnalysisProtocolDraft) {
  if (value.method_id !== props.method?.id || value.project_id !== props.method.project_id)
    throw new Error("Analysis Protocol draft scope mismatch")
  draft.value = value
  viewedRevision.value = value.current_revision
  setFiles(value.current_revision.files, value.current_revision.reason)
  items.value = [{ ...value, package_digest: value.current_revision.package_digest }, ...items.value.filter(item => item.id !== value.id)]
  clearPreview()
  uncertain.value = false
}
function editFile(path: string, value: string) {
  if (canEdit.value)
    files.value = editAnalysisProtocolFile(files.value, path, value)
}
async function discard() {
  if (busy.value || uncertain.value)
    return false
  if (!dirty.value)
    return true
  return new Promise<boolean>((resolve) => {
    dialog.warning({ title: t("page.analysisProtocolDraft.unsavedTitle"), content: t("page.analysisProtocolDraft.unsavedHint"), positiveText: t("page.analysisProtocolDraft.discard"), negativeText: t("common.cancel"), onPositiveClick: () => resolve(true), onNegativeClick: () => resolve(false), onClose: () => resolve(false), onMaskClick: () => resolve(false) })
  })
}
async function close() {
  if (await discard())
    emit("update:show", false)
}
async function newDraft(targetProtocolId?: string) {
  if (!props.method || !supported.value || !await discard())
    return
  const current = ++sequence
  loading.value = true
  error.value = ""
  notice.value = ""
  draft.value = null
  viewedRevision.value = null
  template.value = null
  setFiles({}, "")
  clearPreview()
  try {
    const result = await fetchAnalysisProtocolTemplate(props.method.id, targetProtocolId)
    if (current !== sequence || !props.show)
      return
    if (result.method_id !== props.method.id || result.project_id !== props.method.project_id)
      throw new Error("Analysis Protocol template scope mismatch")
    template.value = result
    setFiles(result.files, "")
  }
  catch (cause) { error.value = errorText(cause) }
  finally {
    if (current === sequence)
      loading.value = false
  }
}
async function openDraft(id: string) {
  if (!await discard())
    return
  const current = ++sequence
  loading.value = true
  error.value = ""
  notice.value = ""
  draft.value = null
  template.value = null
  viewedRevision.value = null
  setFiles({}, "")
  clearPreview()
  try {
    const value = await fetchAnalysisProtocolDraft(id)
    if (current === sequence && props.show)
      acceptDraft(value)
  }
  catch (cause) { error.value = errorText(cause) }
  finally {
    if (current === sequence)
      loading.value = false
  }
}
async function reloadDraft() {
  if (!draft.value || busy.value || (!uncertain.value && !await discard()))
    return
  const current = ++sequence
  loading.value = true
  error.value = ""
  try {
    const value = await fetchAnalysisProtocolDraft(draft.value.id)
    if (current === sequence && props.show)
      acceptDraft(value)
  }
  catch (cause) { error.value = errorText(cause) }
  finally {
    if (current === sequence)
      loading.value = false
  }
}
async function openRevision(number: number) {
  if (!draft.value || !await discard())
    return
  if (number === draft.value.revision) {
    viewedRevision.value = draft.value.current_revision
    setFiles(viewedRevision.value.files, viewedRevision.value.reason)
    return
  }
  const current = ++sequence
  loading.value = true
  error.value = ""
  try {
    const value = await fetchAnalysisProtocolRevision(draft.value.id, number)
    if (current === sequence && props.show && value.draft_id === draft.value?.id && value.revision === number) {
      viewedRevision.value = value
      setFiles(value.files, value.reason)
    }
  }
  catch (cause) { error.value = errorText(cause) }
  finally {
    if (current === sequence)
      loading.value = false
  }
}
async function previewSave() {
  if (!canEdit.value || !dirty.value || !reason.value.trim())
    return
  busy.value = true
  error.value = ""
  notice.value = ""
  try {
    const data = { files: { ...files.value }, reason: reason.value.trim() }
    if (draft.value) {
      const payload = { ...data, expected_revision: draft.value.revision }
      saveRequest.value = payload
      preview.value = await previewAnalysisProtocolRevision(draft.value.id, payload)
    }
    else if (template.value) {
      const payload = { ...data, method_id: template.value.method_id, target_protocol_id: template.value.target_protocol_id, base_protocol_version_id: template.value.base_protocol_version_id }
      saveRequest.value = payload
      preview.value = await previewAnalysisProtocolDraft(payload)
    }
    previewMode.value = "save"
    key.value = createWorkflowId()
    acknowledged.value = false
  }
  catch (cause) { error.value = errorText(cause) }
  finally { busy.value = false }
}
async function previewPublish() {
  if (!draft.value || !draft.value.permissions.can_publish || draft.value.state !== "reviewed" || locked.value || dirty.value || historical.value)
    return
  busy.value = true
  error.value = ""
  notice.value = ""
  try {
    publishRequest.value = analysisProtocolPublishRequest(draft.value)
    preview.value = await previewAnalysisProtocolPublish(draft.value.id, publishRequest.value)
    previewMode.value = "publish"
    acknowledged.value = false
  }
  catch (cause) { error.value = errorText(cause) }
  finally { busy.value = false }
}
async function confirmPreview() {
  if (!preview.value || !acknowledged.value || busy.value)
    return
  busy.value = true
  error.value = ""
  try {
    const confirmation = { preview_digest: preview.value.preview_digest, preview_token: preview.value.preview_token }
    let value: AnalysisProtocolDraft
    if (previewMode.value === "publish" && draft.value && publishRequest.value)
      value = await publishAnalysisProtocolDraft(draft.value.id, { ...publishRequest.value, ...confirmation })
    else if (saveRequest.value && "expected_revision" in saveRequest.value && draft.value)
      value = await confirmAnalysisProtocolRevision(draft.value.id, { ...saveRequest.value, ...confirmation, idempotency_key: key.value })
    else if (saveRequest.value && "method_id" in saveRequest.value)
      value = await confirmAnalysisProtocolDraft({ ...saveRequest.value, ...confirmation, idempotency_key: key.value })
    else
      return
    const published = previewMode.value === "publish"
    acceptDraft(value)
    notice.value = t(published ? "page.analysisProtocolDraft.publishSaved" : "page.analysisProtocolDraft.revisionSaved")
  }
  catch (cause) {
    uncertain.value = isUncertain(cause)
    error.value = errorText(cause)
  }
  finally { busy.value = false }
}
async function review(decision: "reviewed" | "rejected") {
  if (!draft.value || !canReview.value)
    return
  busy.value = true
  error.value = ""
  notice.value = ""
  try {
    acceptDraft(await reviewAnalysisProtocolDraft(draft.value.id, analysisProtocolReviewRequest(draft.value, decision, reviewNote.value.trim())))
    notice.value = t("page.analysisProtocolDraft.reviewSaved")
  }
  catch (cause) {
    uncertain.value = isUncertain(cause)
    error.value = errorText(cause)
  }
  finally { busy.value = false }
}
watch(() => [props.show, props.method?.id] as const, async ([show]) => {
  sequence++
  if (!show)
    return
  draft.value = null
  viewedRevision.value = null
  template.value = null
  items.value = []
  setFiles({}, "")
  clearPreview()
  uncertain.value = false
  error.value = ""
  notice.value = ""
  if (!props.method || !supported.value)
    return
  const current = sequence
  loading.value = true
  try {
    const result = await fetchAnalysisProtocolDrafts(props.method.id)
    if (current !== sequence || !props.show)
      return
    items.value = result.items
    if (result.items.length)
      await openDraft(result.items[0].id)
    else
      await newDraft()
  }
  catch (cause) { error.value = errorText(cause) }
  finally {
    if (current === sequence)
      loading.value = false
  }
}, { immediate: true })
watch(dirty, () => {
  reviewAcknowledged.value = false
})
function protect(event: BeforeUnloadEvent) {
  if (props.show && (busy.value || uncertain.value || dirty.value)) {
    event.preventDefault()
    event.returnValue = ""
  }
}
window.addEventListener("beforeunload", protect)
onBeforeUnmount(() => {
  sequence++
  window.removeEventListener("beforeunload", protect)
})
onBeforeRouteLeave(() => !props.show || discard())
onBeforeRouteUpdate(() => !props.show || discard())
</script>

<style scoped>
.draft-dialog { overflow-wrap: anywhere; }
.draft-controls { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.draft-controls :deep(.n-select) { flex: 1 1 16rem; min-width: 0; }
.draft-box { min-width: 0; margin-top: 12px; padding: 12px; border: 1px solid #e2e8f0; border-radius: 8px; }
.draft-code { font-family: var(--aira-font-mono, monospace); font-size: 13px; line-height: 1.65; white-space: pre-wrap; overflow-wrap: anywhere; max-height: 30rem; overflow: auto; }
.draft-break, .draft-file-manifest { overflow-wrap: anywhere; }
.draft-file-manifest { padding-left: 20px; }
.draft-file-manifest li + li { margin-top: 10px; }
.draft-dialog :deep(.aimd-editor) { max-width: 100%; min-width: 0; }
@media (max-width: 640px) { .draft-box { padding: 10px; } .draft-controls :deep(.n-select) { flex-basis: 100%; } }
</style>
