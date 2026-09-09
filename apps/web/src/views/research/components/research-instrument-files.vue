<template>
  <n-button secondary size="small" data-testid="instrument-files-open" @click="openFiles">
    {{ $t("page.instrumentFiles.title") }}
  </n-button>
  <n-modal
    v-model:show="open"
    preset="card"
    class="aira-dialog instrument-files-dialog"
    style="--aira-dialog-width: 58rem"
    :title="$t('page.instrumentFiles.title')"
    :mask-closable="false"
    :closable="!busy && !selected"
    :close-on-esc="!busy && !selected"
    @after-leave="reset"
  >
    <section data-testid="instrument-files" aria-live="polite">
      <div class="mb-3 flex flex-wrap items-center justify-between gap-2">
        <p class="aira-type-meta m-0">
          {{ $t("page.instrumentFiles.hint") }}
        </p>
        <n-button size="small" :loading="loading" :disabled="!!selected" @click="loadFiles">
          {{ $t("common.refresh") }}
        </n-button>
      </div>
      <n-alert v-if="error" type="error" class="mb-3">
        {{ $t("page.instrumentFiles.loadError") }}
      </n-alert>
      <n-spin :show="loading">
        <template v-if="snapshot">
          <div class="file-scope mb-4">
            <div class="aira-type-label">
              {{ $t("page.instrumentFiles.destination") }} · {{ snapshot.context.lab_name }} /
              {{ snapshot.context.project_name }}
            </div>
            <p class="aira-type-meta my-2">
              {{ $t("page.instrumentFiles.scopeHint") }}
            </p>
            <n-tag :type="snapshot.state === 'delivered' ? 'success' : 'warning'">
              {{ $t(`page.instrumentFiles.delivery.${snapshot.state}`) }}
            </n-tag>
          </div>
          <n-alert v-if="snapshot.state === 'awaiting_files'" type="info" class="mb-4">
            {{ $t("page.instrumentFiles.pendingHint") }}
          </n-alert>
          <n-alert v-if="!snapshot.permissions.associate" type="info" class="mb-4">
            {{ $t("page.instrumentFiles.readOnly") }}
          </n-alert>
          <article
            v-for="file in snapshot.items"
            :key="file.id"
            class="file-card"
            :data-testid="`instrument-output-${file.id}`"
          >
            <div class="file-card-header">
              <div class="min-w-0 flex-1">
                <h3 class="aira-type-label m-0 break-all">
                  {{ file.name }}
                </h3>
                <p class="aira-type-meta my-2">
                  {{ file.media_type }} · {{ file.byte_size == null ? $t("page.instrumentFiles.sizeLimit") : "" }} {{ formatBytes(file.byte_size ?? file.max_bytes) }} ·
                  {{
                    file.required
                      ? $t("page.instrumentFiles.required")
                      : $t("page.instrumentFiles.optional")
                  }}
                </p>
                <n-tag size="small">
                  {{ $t(`page.instrumentFiles.fileState.${file.state}`) }}
                </n-tag>
              </div>
              <div v-if="file.state === 'registered'" class="flex flex-wrap gap-2">
                <n-button
                  size="small"
                  :loading="downloading === file.id"
                  :disabled="!!downloading"
                  @click="download(file)"
                >
                  {{ $t("page.instrumentFiles.download") }}
                </n-button>
                <n-button
                  v-if="snapshot.permissions.associate"
                  size="small"
                  type="primary"
                  secondary
                  @click="editAssociation(file)"
                >
                  {{
                    file.association
                      ? $t("page.instrumentFiles.changeAssociation")
                      : $t("page.instrumentFiles.associate")
                  }}
                </n-button>
              </div>
            </div>
            <p v-if="file.association?.state === 'restricted'" class="aira-type-meta mt-3">
              {{ $t("page.instrumentFiles.restrictedAssociation") }}
            </p>
            <div v-else-if="file.association?.state === 'associated'" class="mt-3">
              <router-link :to="recordRoute(file.association)" class="file-record-link">
                {{ recordLabel(file.association) }}
              </router-link>
              <p class="aira-type-meta mb-0 whitespace-pre-wrap break-words">
                {{ $t("page.instrumentFiles.sample") }} ·
                {{ file.association.sample_reference || $t("page.instrumentFiles.unspecified") }}
              </p>
            </div>
            <p v-else-if="file.state === 'registered'" class="aira-type-meta mt-3">
              {{ $t("page.instrumentFiles.unassociated") }}
            </p>
            <details v-if="file.state === 'registered'" class="mt-3">
              <summary class="aira-type-meta cursor-pointer">
                {{ $t("page.instrumentFiles.provenance") }}
              </summary>
              <dl class="file-metadata">
                <dt>{{ $t("page.instrumentFiles.acquiredAt") }}</dt><dd>{{ file.captured_at }}</dd> <dt>{{ $t("page.instrumentFiles.receivedAt") }}</dt><dd>{{ file.received_at }}</dd> <dt>{{ $t("page.instrumentFiles.units") }}</dt><dd>
                  {{
                    file.original_units?.join("; ") || $t("page.instrumentFiles.unspecified")
                  }}
                </dd>
                <dt>{{ $t("page.instrumentFiles.conversions") }}</dt><dd>
                  {{
                    file.conversion_rules?.join("; ") || $t("page.instrumentFiles.noConversion")
                  }}
                </dd>
                <dt>{{ $t("page.instrumentFiles.completionReference") }}</dt><dd>{{ file.completion_reference }}</dd> <dt>SHA-256</dt><dd>{{ file.sha256 }}</dd> <dt>{{ $t("page.instrumentFiles.assetVersion") }}</dt><dd>{{ file.data_asset_version_id }}</dd>
              </dl>
            </details>
            <n-button
              v-if="file.state === 'registered'"
              text
              size="small"
              class="mt-3"
              :loading="historyLoading === file.id"
              @click="loadHistory(file)"
            >
              {{ $t("page.instrumentFiles.history") }}
            </n-button>
            <n-alert v-if="historyError === file.id" type="error" class="mt-2">
              {{ $t("page.instrumentFiles.loadError") }}
            </n-alert>
            <div v-if="histories[file.id]" class="file-history mt-2">
              <p v-if="!histories[file.id].items.length" class="aira-type-meta">
                {{ $t("page.instrumentFiles.noHistory") }}
              </p>
              <div v-for="entry in histories[file.id].items" :key="entry.id" class="mb-3">
                <span class="aira-type-meta">#{{ entry.revision }} · {{ entry.associated_at }} ·
                  {{
                    entry.id === file.association?.id
                      ? $t("page.instrumentFiles.current")
                      : $t("page.instrumentFiles.previous")
                  }}</span>
                <p v-if="entry.state === 'restricted'" class="aira-type-meta m-0">
                  {{ $t("page.instrumentFiles.restrictedAssociation") }}
                </p>
                <template v-else>
                  <div>
                    <router-link :to="recordRoute(entry)" class="file-record-link">
                      {{ recordLabel(entry) }}
                    </router-link>
                  </div>
                  <p class="aira-type-meta m-0 whitespace-pre-wrap break-words">
                    {{ entry.sample_reference || $t("page.instrumentFiles.unspecified") }}
                  </p>
                </template>
              </div>
              <n-button
                v-if="histories[file.id].has_more"
                size="small"
                :loading="historyLoading === file.id"
                @click="loadHistory(file, true)"
              >
                {{ $t("page.instrumentFiles.more") }}
              </n-button>
            </div>
          </article>
        </template>
      </n-spin>
      <n-alert v-if="downloadError" type="error" class="mt-3">
        {{ $t("page.instrumentFiles.downloadError") }}
      </n-alert>
      <n-alert v-if="saved" type="success" class="mt-3" data-testid="instrument-association-saved">
        {{ $t("page.instrumentFiles.saved") }}
      </n-alert>
    </section>
  </n-modal>
  <n-modal
    :show="!!selected"
    preset="card"
    class="aira-dialog instrument-association-dialog"
    style="--aira-dialog-width: 44rem"
    :title="$t('page.instrumentFiles.associate')"
    :mask-closable="false"
    :closable="!busy"
    :close-on-esc="!busy"
    @update:show="closeEditor"
  >
    <section data-testid="instrument-association">
      <n-alert type="info" class="mb-3">
        {{ $t("page.instrumentFiles.associationHint") }}
      </n-alert>
      <n-alert v-if="editError" type="error" class="mb-3">
        {{ $t(uncertain ? "page.instrumentFiles.uncertain" : "page.instrumentFiles.editError") }}
      </n-alert>
      <template v-if="selected && snapshot">
        <p class="aira-type-label break-all">
          {{ selected.name }}
        </p>
        <p class="aira-type-meta">
          {{ snapshot.context.lab_name }} / {{ snapshot.context.project_name }}
        </p>
        <n-form v-if="!preview" label-placement="top" :disabled="busy">
          <n-form-item :label="$t('page.instrumentFiles.protocol')" required>
            <n-select
              :value="protocolId"
              filterable
              remote
              :options="protocols"
              :loading="protocolLoading"
              :placeholder="$t('page.instrumentFiles.protocolSearch')"
              data-testid="instrument-record-protocol"
              @search="searchProtocols"
              @update:value="selectProtocol"
            />
          </n-form-item>
          <n-button
            v-if="protocolMore"
            size="small"
            class="mb-3"
            :loading="protocolLoading"
            @click="loadProtocols(true)"
          >
            {{ $t("page.instrumentFiles.moreProtocols") }}
          </n-button>
          <n-form-item :label="$t('page.instrumentFiles.recordSearch')">
            <n-input-group>
              <n-input
                v-model:value="recordQuery"
                :disabled="!protocolId"
                :maxlength="200"
                :placeholder="$t('page.instrumentFiles.recordSearchHint')"
                @keydown.enter.prevent="searchRecords"
              />
              <n-button :disabled="!protocolId" :loading="recordLoading" @click="searchRecords">
                {{ $t("common.search") }}
              </n-button>
            </n-input-group>
          </n-form-item>
          <n-form-item :label="$t('page.instrumentFiles.recordVersion')" required>
            <n-select
              v-model:value="recordKey"
              :options="recordOptions"
              :loading="recordLoading"
              :disabled="!protocolId || recordLoading"
              data-testid="instrument-record-version"
            />
          </n-form-item>
          <p v-if="protocolId && !recordLoading && !records.length" class="aira-type-meta">
            {{ $t("page.instrumentFiles.noRecords") }}
          </p>
          <n-button
            v-if="recordMore"
            size="small"
            class="mb-3"
            :loading="recordLoading"
            @click="loadRecords(true)"
          >
            {{ $t("page.instrumentFiles.more") }}
          </n-button>
          <n-form-item :label="$t('page.instrumentFiles.sample')">
            <n-input
              v-model:value="sample"
              type="textarea"
              :maxlength="1024"
              :autosize="{ minRows: 2, maxRows: 5 }"
              :placeholder="$t('page.instrumentFiles.sampleHint')"
              data-testid="instrument-sample-reference"
            />
          </n-form-item>
        </n-form>
        <template v-else>
          <n-alert type="warning">
            {{ $t("page.instrumentFiles.confirmHint") }}
          </n-alert>
          <dl class="file-metadata">
            <dt>{{ $t("page.instrumentFiles.recordVersion") }}</dt><dd>
              <router-link :to="recordRoute(preview.record)">
                {{ recordLabel(preview.record) }}
              </router-link>
            </dd>
            <dt>Record ID</dt><dd>{{ preview.record.record_id }} · v{{ preview.record.record_version }}</dd>
            <dt>{{ $t("page.instrumentFiles.recordHash") }}</dt><dd>{{ preview.command.record_hash }}</dd>
            <dt>{{ $t("page.instrumentFiles.assetVersion") }}</dt><dd>{{ preview.output.data_asset_version_id }}</dd> <dt>SHA-256</dt><dd>{{ preview.output.sha256 }}</dd> <dt>{{ $t("page.instrumentFiles.sample") }}</dt><dd>
              {{
                preview.command.sample_reference || $t("page.instrumentFiles.unspecified")
              }}
            </dd>
          </dl>
        </template>
      </template>
    </section>
    <template #footer>
      <div class="flex flex-wrap justify-end gap-2">
        <n-button :disabled="busy" @click="closeEditor">
          {{ $t("common.cancel") }}
        </n-button>
        <n-button v-if="preview && !uncertain" :disabled="busy" @click="preview = null">
          {{ $t("page.research.backToEdit") }}
        </n-button>
        <n-button v-if="uncertain" :disabled="busy" @click="checkSaved">
          {{ $t("page.instrumentFiles.checkSaved") }}
        </n-button>
        <n-button
          type="primary"
          :disabled="!preview && (!recordKey || protocolLoading || recordLoading)"
          :loading="busy"
          @click="saveAssociation"
        >
          {{ preview ? $t("common.confirm") : $t("common.preview") }}
        </n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import type {
  InstrumentAssociationDraft,
  InstrumentAssociationHistory,
  InstrumentAssociationPreview,
  InstrumentOutput,
  InstrumentOutputs,
  InstrumentPage,
  InstrumentRecordOption,
} from "@/service/api/instrument-outputs"
import {
  confirmInstrumentAssociation,
  fetchInstrumentAssociationHistory,
  fetchInstrumentOutputs,
  fetchInstrumentRecordOptions,
  previewInstrumentAssociation,
} from "@/service/api/instrument-outputs"
import { fetchResearchFile } from "@/service/api/knowledge"
import { fetchProtocols } from "@/service/api/project-protocols"
import { $t } from "@airalogy/shared/locales"

const props = defineProps<{ jobId: string }>()
const emit = defineEmits<{ changed: [] }>()
const open = ref(false)
const loading = ref(false)
const error = ref(false)
const snapshot = ref<InstrumentOutputs | null>(null)
const selected = ref<InstrumentOutput | null>(null)
const busy = ref(false)
const editError = ref(false)
const uncertain = ref(false)
const saved = ref(false)
const preview = ref<InstrumentAssociationPreview | null>(null)
const pending = ref<InstrumentAssociationDraft | null>(null)
const protocols = ref<{ label: string, value: string }[]>([])
const protocolId = ref<string | null>(null)
const protocolQuery = ref("")
const protocolPage = ref(1)
const protocolMore = ref(false)
const protocolLoading = ref(false)
const records = ref<InstrumentRecordOption[]>([])
const recordKey = ref<string | null>(null)
const recordQuery = ref("")
const recordOffset = ref(0)
const recordMore = ref(false)
const recordLoading = ref(false)
const sample = ref("")
const histories = ref<Record<string, InstrumentPage<InstrumentAssociationHistory>>>({})
const historyLoading = ref("")
const historyError = ref("")
const downloading = ref("")
const downloadError = ref(false)
let epoch = 0
let protocolEpoch = 0
let recordEpoch = 0
const key = (record: InstrumentRecordOption) => `${record.record_id}:${record.record_version}`
const recordOptions = computed(() =>
  records.value.map(record => ({ value: key(record), label: recordLabel(record) })),
)
function recordLabel(record: InstrumentRecordOption) {
  return `${record.protocol_name} · #${record.record_number} · v${record.record_version} · ${$t("page.instrumentFiles.protocolVersion")} ${record.protocol_version}`
}
function recordRoute(record: InstrumentRecordOption) {
  return {
    name: "protocol-record-report" as const,
    params: {
      labUid: snapshot.value?.context.lab_uid,
      projectUid: snapshot.value?.context.project_uid,
      protocolUid: record.protocol_uid,
      protocolVersion: record.protocol_version,
      recordId: record.record_id,
      recordVersion: String(record.record_version),
    },
  }
}
function formatBytes(bytes: number) {
  return bytes < 1024
    ? `${bytes} B`
    : `${(bytes / (bytes < 1048576 ? 1024 : 1048576)).toFixed(1)} ${bytes < 1048576 ? "KiB" : "MiB"}`
}
function reset() {
  epoch++
  protocolEpoch++
  recordEpoch++
  snapshot.value = null
  selected.value = null
  preview.value = null
  pending.value = null
  histories.value = {}
  saved.value = false
  error.value = false
  downloadError.value = false
  downloading.value = ""
  historyLoading.value = ""
  historyError.value = ""
  loading.value = false
  busy.value = false
  protocolLoading.value = false
  recordLoading.value = false
}
watch(
  () => props.jobId,
  () => {
    open.value = false
    reset()
  },
)
onBeforeUnmount(reset)
async function openFiles() {
  reset()
  open.value = true
  await loadFiles()
}
async function loadFiles() {
  const current = ++epoch
  snapshot.value = null
  histories.value = {}
  error.value = false
  loading.value = true
  try {
    const result = await fetchInstrumentOutputs(props.jobId)
    if (current === epoch)
      snapshot.value = result
  }
  catch {
    if (current === epoch)
      error.value = true
  }
  finally {
    if (current === epoch)
      loading.value = false
  }
}
async function download(file: InstrumentOutput) {
  if (!file.research_file_id || downloading.value)
    return
  const current = epoch
  downloading.value = file.id
  downloadError.value = false
  try {
    const blob = await fetchResearchFile(file.research_file_id, "download")
    if (current !== epoch || !open.value)
      return
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement("a")
    anchor.href = url
    anchor.download = file.name
    anchor.click()
    window.setTimeout(() => URL.revokeObjectURL(url), 60000)
  }
  catch {
    if (current === epoch)
      downloadError.value = true
  }
  finally {
    if (current === epoch)
      downloading.value = ""
  }
}
async function loadHistory(file: InstrumentOutput, more = false) {
  if (historyLoading.value)
    return
  const current = epoch
  historyLoading.value = file.id
  historyError.value = ""
  try {
    const result = await fetchInstrumentAssociationHistory(
      props.jobId,
      file.id,
      more ? histories.value[file.id]?.next_offset : 0,
    )
    if (current === epoch) {
      histories.value[file.id] = {
        ...result,
        items: more
          ? [...histories.value[file.id].items, ...result.items].filter(
              (item, index, all) => all.findIndex(other => other.id === item.id) === index,
            )
          : result.items,
      }
    }
  }
  catch {
    if (current === epoch) {
      delete histories.value[file.id]
      historyError.value = file.id
    }
  }
  finally {
    if (current === epoch)
      historyLoading.value = ""
  }
}
async function editAssociation(file: InstrumentOutput) {
  selected.value = file
  saved.value = false
  preview.value = null
  pending.value = null
  uncertain.value = false
  editError.value = false
  protocols.value = []
  protocolQuery.value = ""
  protocolPage.value = 1
  protocolMore.value = false
  protocolId.value = null
  records.value = []
  recordKey.value = null
  recordQuery.value = ""
  recordMore.value = false
  sample.value = file.association?.state === "associated" ? file.association.sample_reference : ""
  if (file.association?.state === "associated")
    protocolId.value = file.association.protocol_id
  await loadProtocols()
  if (protocolId.value && !records.value.length && !recordLoading.value)
    await loadRecords()
}
function closeEditor() {
  if (busy.value)
    return
  protocolEpoch++
  recordEpoch++
  selected.value = null
  preview.value = null
  pending.value = null
  uncertain.value = false
}
function searchProtocols(query: string) {
  protocolQuery.value = query
  protocolPage.value = 1
  void loadProtocols()
}
async function loadProtocols(more = false) {
  if (!snapshot.value)
    return
  const current = ++protocolEpoch
  const page = more ? protocolPage.value + 1 : 1
  protocolLoading.value = true
  editError.value = false
  try {
    const result = await fetchProtocols({
      projectId: snapshot.value.context.project_id,
      page,
      pageSize: 25,
      name: protocolQuery.value || undefined,
    })
    if (result.error || !result.data)
      throw new Error("Protocol options unavailable")
    if (current !== protocolEpoch || !selected.value)
      return
    const items = result.data.protocols.map(item => ({
      value: String(item.id),
      label: `${item.name} · ${item.uid}`,
    }))
    protocols.value = more ? [...protocols.value, ...items] : items
    if (
      selected.value.association?.state === "associated"
      && !protocols.value.some(item => item.value === protocolId.value)
    ) {
      protocols.value.unshift({
        value: selected.value.association.protocol_id,
        label: selected.value.association.protocol_name,
      })
    }
    protocolPage.value = page
    protocolMore.value = page * 25 < result.data.total_count
    if (!protocolId.value && result.data.total_count === 1) {
      protocolId.value = items[0]?.value || null
      await loadRecords()
    }
  }
  catch {
    if (current === protocolEpoch) {
      protocols.value = []
      editError.value = true
    }
  }
  finally {
    if (current === protocolEpoch)
      protocolLoading.value = false
  }
}
async function selectProtocol(value: string) {
  protocolId.value = value
  recordQuery.value = ""
  recordKey.value = null
  await loadRecords()
}
async function searchRecords() {
  recordKey.value = null
  await loadRecords()
}
async function loadRecords(more = false) {
  if (!protocolId.value)
    return
  const current = ++recordEpoch
  recordLoading.value = true
  editError.value = false
  if (!more) {
    records.value = []
    recordKey.value = null
    recordMore.value = false
  }
  try {
    const result = await fetchInstrumentRecordOptions(
      props.jobId,
      protocolId.value,
      recordQuery.value,
      more ? recordOffset.value : 0,
    )
    if (current !== recordEpoch || !selected.value)
      return
    records.value = more ? [...records.value, ...result.items] : result.items
    recordOffset.value = result.next_offset
    recordMore.value = result.has_more
    // A unique option is convenient, but the exact version still appears in confirmation.
    if (records.value.length === 1 && !result.has_more)
      recordKey.value = key(records.value[0])
  }
  catch {
    if (current === recordEpoch) {
      records.value = []
      recordKey.value = null
      editError.value = true
    }
  }
  finally {
    if (current === recordEpoch)
      recordLoading.value = false
  }
}
async function saveAssociation() {
  if (busy.value || !selected.value)
    return
  busy.value = true
  editError.value = false
  const current = epoch
  try {
    if (!preview.value) {
      const record = records.value.find(item => key(item) === recordKey.value)
      if (!record)
        return
      const draft = {
        id: crypto.randomUUID(),
        record_id: record.record_id,
        record_version: record.record_version,
        sample_reference: sample.value,
        expected_association_id: selected.value.association?.id || null,
      }
      const result = await previewInstrumentAssociation(props.jobId, selected.value.id, draft)
      if (current !== epoch)
        return
      pending.value = draft
      preview.value = result
    }
    else if (pending.value) {
      // Keep the same immutable draft/digest after response loss. Never create a second write on retry.
      uncertain.value = true
      await confirmInstrumentAssociation(
        props.jobId,
        selected.value.id,
        pending.value,
        preview.value.preview_digest,
      )
      if (current !== epoch)
        return
      selected.value = null
      preview.value = null
      pending.value = null
      uncertain.value = false
      await loadFiles()
      saved.value = open.value && snapshot.value?.job_id === props.jobId && !error.value
      emit("changed")
    }
  }
  catch {
    if (current === epoch)
      editError.value = true
  }
  finally {
    busy.value = false
  }
}
async function checkSaved() {
  if (!selected.value || !pending.value)
    return
  busy.value = true
  const current = epoch
  try {
    const result = await fetchInstrumentOutputs(props.jobId)
    if (current !== epoch)
      return
    const found = result.items.find(item => item.id === selected.value!.id)
    snapshot.value = result
    histories.value = {}
    if (found?.association?.id === pending.value.id) {
      selected.value = null
      preview.value = null
      pending.value = null
      uncertain.value = false
      saved.value = true
      emit("changed")
    }
    else {
      selected.value = found || null
      preview.value = null
      pending.value = null
      uncertain.value = false
      editError.value = true
      records.value = []
      recordKey.value = null
    }
  }
  catch {
    if (current === epoch) {
      snapshot.value = null
      histories.value = {}
      editError.value = true
    }
  }
  finally {
    busy.value = false
  }
}
</script>

<style scoped>
.file-card,
.file-scope {
  border: 1px solid var(--n-border-color, #e5e7eb);
  border-radius: 0.75rem;
  padding: 1rem;
  margin-bottom: 0.875rem;
  min-width: 0;
}
.file-scope {
  background: #f8fafc;
}
.file-card-header {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 0.75rem;
  align-items: start;
}
@media (min-width: 640px) {
  .file-card-header {
    grid-template-columns: minmax(0, 1fr) auto;
  }
}
.file-metadata {
  display: grid;
  grid-template-columns: minmax(6rem, 0.3fr) minmax(0, 1fr);
  gap: 0.5rem 1rem;
  font-size: var(--aira-font-size-meta, 0.875rem);
}
.file-metadata dt {
  color: #64748b;
}
.file-metadata dd {
  margin: 0;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}
.file-record-link {
  color: #0877c9;
  text-decoration: underline;
  overflow-wrap: anywhere;
}
.file-history {
  border-left: 2px solid #e5e7eb;
  padding-left: 0.75rem;
}
@media (max-width: 480px) {
  .file-metadata {
    grid-template-columns: minmax(0, 1fr);
    gap: 0.25rem;
  }
  .file-metadata dd {
    margin-bottom: 0.5rem;
  }
}
</style>
