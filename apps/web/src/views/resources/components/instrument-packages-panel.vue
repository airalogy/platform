<script setup lang="ts">
import type { AdapterImportPreview, AdapterRelease, AdapterReview } from "@/service/api/instrument-packages"
import { confirmAdapterImport, confirmAdapterReview, fetchAdapterHistory, fetchAdapterPackages, previewAdapterImport, previewAdapterReview } from "@/service/api/instrument-packages"
import { fetchResearchFile } from "@/service/api/knowledge"
import { $t } from "@airalogy/shared/locales"

const props = defineProps<{ labId: string }>()
const items = ref<AdapterRelease[]>([])
const hasMore = ref(false)
const busy = ref(false)
const showImport = ref(false)
const input = ref<HTMLInputElement | null>(null)
const file = shallowRef<File | null>(null)
const requestId = ref("")
const preview = ref<AdapterImportPreview | null>(null)
const selected = ref<AdapterRelease | null>(null)
const history = ref<Awaited<ReturnType<typeof fetchAdapterHistory>>["items"]>([])
const review = reactive<AdapterReview>({ expected_revision: 1, operation: "approve_source", reason: "", source_reviewed: false })
const reviewDigest = ref("")

async function guarded(action: () => Promise<void>) {
  if (busy.value)
    return
  busy.value = true
  try {
    await action()
  }
  catch { window.$message?.error($t("page.resourceLibrary.adapterRetry")) }
  finally { busy.value = false }
}
async function refresh(more = false) {
  const result = await fetchAdapterPackages(props.labId, more ? items.value.length : 0)
  items.value = more ? [...items.value, ...result.items] : result.items
  hasMore.value = result.has_more
}
function openImport() {
  file.value = null
  preview.value = null
  requestId.value = crypto.randomUUID()
  showImport.value = true
}
function chooseFile(event: Event) {
  preview.value = null
  const next = (event.target as HTMLInputElement).files?.[0]
  if (!next || next.size === 0 || next.size > 64 * 1024 * 1024) {
    file.value = null
    window.$message?.error($t("page.resourceLibrary.adapterFileLimit"))
    return
  }
  file.value = next
}
async function importStep() {
  if (!file.value)
    return
  await guarded(async () => {
    if (!preview.value) {
      preview.value = await previewAdapterImport(props.labId, requestId.value, file.value!)
      return
    }
    const saved = await confirmAdapterImport(props.labId, requestId.value, file.value!, preview.value.preview_digest)
    showImport.value = false
    await refresh()
    await openRelease(saved)
    window.$message?.success($t("page.resourceLibrary.adapterSaved"))
  })
}
async function openRelease(item: AdapterRelease) {
  selected.value = item
  history.value = []
  reviewDigest.value = ""
  Object.assign(review, { expected_revision: item.revision, operation: item.state === "approved" ? "revoke" : "approve_source", reason: "", source_reviewed: false })
  history.value = (await fetchAdapterHistory(item.id)).items
}
async function reviewStep() {
  if (!selected.value)
    return
  await guarded(async () => {
    if (!reviewDigest.value) {
      reviewDigest.value = (await previewAdapterReview(selected.value!.id, review)).preview_digest
      return
    }
    const updated = await confirmAdapterReview(selected.value!.id, { ...review, preview_digest: reviewDigest.value })
    await refresh()
    await openRelease(updated)
    window.$message?.success($t("page.resourceLibrary.adapterReviewSaved"))
  })
}
async function download(item: AdapterRelease) {
  const blob = await fetchResearchFile(item.research_file_id, "download")
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement("a")
  anchor.href = url
  anchor.download = `${item.package_key}-${item.package_version}.zip`
  anchor.click()
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
}
onMounted(() => guarded(() => refresh()))
</script>

<template>
  <section class="my-6 min-w-0" data-testid="instrument-packages-panel">
    <h3 class="mb-2">
      {{ $t("page.resourceLibrary.adapterPackagesTitle") }}
    </h3>
    <p class="mb-3">
      {{ $t("page.resourceLibrary.adapterPackagesHint") }}
    </p>
    <n-space class="mb-3">
      <n-button :disabled="busy" @click="openImport">
        {{ $t("page.resourceLibrary.adapterImport") }}
      </n-button>
      <n-button :loading="busy" @click="guarded(() => refresh())">
        {{ $t("common.refresh") }}
      </n-button>
    </n-space>
    <n-empty v-if="!items.length && !busy" :description="$t('page.resourceLibrary.adapterEmpty')" />
    <div v-for="item in items" :key="item.id" class="mb-3 min-w-0 border border-gray-200 rounded-lg p-3" data-testid="adapter-release">
      <div class="flex flex-wrap items-center gap-2">
        <strong class="break-all">{{ item.package_key }} · {{ item.package_version }}</strong>
        <n-tag size="small">
          {{ $t(`page.resourceLibrary.adapterState.${item.state}`) }}
        </n-tag>
        <n-button size="small" :disabled="busy" @click="guarded(() => openRelease(item))">
          {{ $t("page.resourceLibrary.adapterInspect") }}
        </n-button>
      </div>
      <code class="mt-2 block break-all text-xs">SHA-256: {{ item.archive_digest }}</code>
    </div>
    <n-button v-if="hasMore" :loading="busy" @click="guarded(() => refresh(true))">
      {{ $t("page.resourceLibrary.adapterMore") }}
    </n-button>

    <n-modal v-model:show="showImport" preset="card" class="aira-dialog" :title="$t('page.resourceLibrary.adapterImport')" :mask-closable="false" style="--aira-dialog-width: 44rem">
      <n-alert type="warning" class="mb-3">
        {{ $t("page.resourceLibrary.adapterImportImpact") }}<br>Lab: {{ labId }}
      </n-alert>
      <input ref="input" type="file" accept=".zip,application/zip" class="max-w-full" :disabled="busy || !!preview" data-testid="adapter-upload" :aria-label="$t('page.resourceLibrary.adapterImport')" @change="chooseFile">
      <template v-if="preview">
        <p class="mt-3 break-all">
          {{ preview.inspection.manifest.id }} · {{ preview.inspection.manifest.version }}
        </p>
        <code class="block break-all">{{ preview.inspection.archive_digest }}</code>
        <n-alert v-if="preview.existing_release_id" type="info" class="mt-3">
          {{ $t("page.resourceLibrary.adapterDuplicate") }}
        </n-alert>
        <pre class="mt-3 max-h-72 overflow-auto whitespace-pre-wrap break-all text-xs" data-testid="adapter-import-preview">{{ JSON.stringify(preview.inspection.manifest, null, 2) }}</pre>
      </template>
      <template #footer>
        <n-space justify="end">
          <n-button :disabled="busy" @click="showImport = false">
            {{ $t("common.cancel") }}
          </n-button>
          <n-button v-if="preview" :disabled="busy" @click="preview = null">
            {{ $t("common.previous") }}
          </n-button>
          <n-button type="primary" :disabled="!file" :loading="busy" @click="importStep">
            {{ preview ? $t("common.confirm") : $t("common.preview") }}
          </n-button>
        </n-space>
      </template>
    </n-modal>

    <n-modal :show="!!selected" preset="card" class="aira-dialog" :title="$t('page.resourceLibrary.adapterInspect')" :mask-closable="false" style="--aira-dialog-width: 48rem" @update:show="selected = null">
      <template v-if="selected">
        <n-alert type="warning" class="mb-3">
          {{ $t("page.resourceLibrary.adapterAuthorityHint") }}
        </n-alert>
        <h4 class="break-all">
          {{ selected.package_key }} · {{ selected.package_version }}
        </h4>
        <p>{{ $t(`page.resourceLibrary.adapterState.${selected.state}`) }}</p>
        <code class="my-2 block break-all">SHA-256: {{ selected.archive_digest }}</code>
        <n-button class="mb-3" :disabled="busy" @click="guarded(() => download(selected!))">
          {{ $t("page.resourceLibrary.adapterDownload") }}
        </n-button>
        <n-collapse class="mb-3">
          <n-collapse-item :title="$t('page.resourceLibrary.adapterManifest')" name="manifest">
            <pre class="max-h-72 overflow-auto whitespace-pre-wrap break-all text-xs">{{ JSON.stringify(selected.inspection.manifest, null, 2) }}</pre>
          </n-collapse-item>
          <n-collapse-item :title="$t('page.resourceLibrary.adapterHistory')" name="history">
            <p v-for="entry in history" :key="entry.revision" class="mb-2 break-words">
              #{{ entry.revision }} · {{ $t(`page.resourceLibrary.adapterState.${entry.action as AdapterRelease['state']}`) }} · {{ new Date(entry.created_at).toLocaleString() }}<br>{{ entry.reason }}<br>{{ entry.actor_user_id }}
            </p>
          </n-collapse-item>
        </n-collapse>
        <template v-if="selected.state !== 'revoked'">
          <n-select v-model:value="review.operation" class="mb-3" :disabled="!!reviewDigest || busy" :options="selected.state === 'imported' ? [{ label: $t('page.resourceLibrary.adapterApprove'), value: 'approve_source' }, { label: $t('page.resourceLibrary.adapterRevoke'), value: 'revoke' }] : [{ label: $t('page.resourceLibrary.adapterRevoke'), value: 'revoke' }]" />
          <n-form-item :label="$t('page.resourceLibrary.changeReason')" required>
            <n-input v-model:value="review.reason" :disabled="!!reviewDigest || busy" type="textarea" data-testid="adapter-review-reason" />
          </n-form-item>
          <n-checkbox v-if="review.operation === 'approve_source'" v-model:checked="review.source_reviewed" :disabled="!!reviewDigest || busy">
            {{ $t("page.resourceLibrary.adapterSourceReviewed") }}
          </n-checkbox>
          <n-alert v-if="reviewDigest" class="mt-3" type="warning">
            {{ review.operation === 'revoke' ? $t("page.resourceLibrary.adapterRevokeImpact") : $t("page.resourceLibrary.adapterApproveImpact") }}
          </n-alert>
        </template>
      </template>
      <template #footer>
        <n-space justify="end">
          <n-button :disabled="busy" @click="selected = null">
            {{ $t("common.close") }}
          </n-button>
          <n-button v-if="reviewDigest" :disabled="busy" @click="reviewDigest = ''">
            {{ $t("common.previous") }}
          </n-button>
          <n-button v-if="selected && selected.state !== 'revoked'" type="primary" :loading="busy" :disabled="!review.reason.trim() || (review.operation === 'approve_source' && !review.source_reviewed)" @click="reviewStep">
            {{ reviewDigest ? $t("common.confirm") : $t("common.preview") }}
          </n-button>
        </n-space>
      </template>
    </n-modal>
  </section>
</template>
