<template>
  <section class="research-assets-panel">
    <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
      <div>
        <div class="aira-type-eyebrow">
          {{ $t("page.research.scientificAssets") }}
        </div>
        <h2 class="aira-type-section-title mb-0 mt-1">
          {{ $t("page.research.resultsAndEvidence") }}
        </h2>
        <p class="aira-type-meta aira-text-secondary mb-0 mt-2">
          {{ $t("page.research.scientificAssetsHint") }}
        </p>
      </div>
      <div class="flex flex-wrap gap-2">
        <n-button size="small" secondary @click="openModal('asset')">
          {{ $t("page.research.addDataAsset") }}
        </n-button>
        <n-button size="small" secondary @click="openModal('evidence')">
          {{ $t("page.research.addEvidence") }}
        </n-button>
        <n-button size="small" type="primary" @click="openModal('claim')">
          {{ $t("page.research.addClaim") }}
        </n-button>
        <n-button
          size="small"
          type="primary"
          secondary
          :disabled="!knowledgeEvidenceOptions.length"
          @click="openModal('knowledge')"
        >
          {{ $t("page.research.suggestKnowledge") }}
        </n-button>
      </div>
    </div>

    <n-spin :show="loading" class="mt-4 min-h-20">
      <n-alert v-if="loadError" type="error" :title="$t('page.research.assetsLoadError')">
        <n-button size="tiny" class="mt-2" @click="loadAssets">
          {{ $t("common.retry") }}
        </n-button>
      </n-alert>
      <n-empty
        v-else-if="isEmpty"
        class="py-6"
        :description="$t('page.research.noScientificAssets')"
      />
      <n-tabs v-else type="line" animated>
        <n-tab-pane name="claims" :tab="`${$t('page.research.claims')} (${bundle.claims.length})`">
          <div class="space-y-3">
            <article v-for="claim in bundle.claims" :key="claim.id" class="scientific-card">
              <div class="flex flex-wrap items-start justify-between gap-2">
                <div class="min-w-0 flex-1">
                  <div class="flex flex-wrap items-center gap-2">
                    <n-tag size="small" round :type="claimStateType(claim.state)">
                      {{ claimStateLabel(claim.state) }}
                    </n-tag>
                    <span class="aira-type-meta">r{{ claim.revision }}</span>
                    <span v-if="claim.confidence != null" class="aira-type-meta">
                      {{ $t("page.research.confidence") }} {{ Math.round(claim.confidence * 100) }}%
                    </span>
                  </div>
                  <p class="aira-type-body mb-0 mt-2 whitespace-pre-wrap">
                    {{ claim.statement }}
                  </p>
                  <p v-if="claim.uncertainty" class="aira-type-meta aira-text-secondary mb-0 mt-2 whitespace-pre-wrap">
                    {{ $t("page.research.uncertainty") }} · {{ claim.uncertainty }}
                  </p>
                  <div v-if="claim.evidence.length" class="aira-type-meta mt-2">
                    {{ $t("page.research.linkedEvidenceCount", { count: claim.evidence.length }) }}
                  </div>
                </div>
                <div v-if="claim.state === 'draft' || claim.state === 'suggested'" class="flex gap-1">
                  <n-button size="tiny" type="success" secondary @click="confirmClaimReview(claim, 'reviewed')">
                    {{ $t("page.research.acceptClaim") }}
                  </n-button>
                  <n-button size="tiny" type="error" tertiary @click="confirmClaimReview(claim, 'rejected')">
                    {{ $t("common.reject") }}
                  </n-button>
                </div>
              </div>
            </article>
            <n-empty v-if="!bundle.claims.length" class="py-5" :description="$t('page.research.noClaims')" />
          </div>
        </n-tab-pane>

        <n-tab-pane name="evidence" :tab="`${$t('page.research.evidence')} (${bundle.evidence.length})`">
          <div class="space-y-3">
            <article v-for="item in bundle.evidence" :key="item.id" class="scientific-card">
              <div class="flex flex-wrap items-start justify-between gap-2">
                <div class="min-w-0 flex-1">
                  <div class="flex flex-wrap items-center gap-2">
                    <n-tag size="small" round :type="evidenceStateType(item.quality_state)">
                      {{ evidenceStateLabel(item.quality_state) }}
                    </n-tag>
                    <span class="aira-type-meta">{{ evidenceKindLabel(item.kind) }}</span>
                    <span class="aira-type-meta">{{ artifactTypeLabel(item.artifact_type) }}</span>
                  </div>
                  <p class="aira-type-body mb-0 mt-2">
                    {{ item.summary || artifactLabel(item) }}
                  </p>
                  <div class="aira-type-meta mt-1 break-all">
                    {{ artifactLabel(item) }}
                  </div>
                </div>
                <div v-if="item.quality_state === 'pending'" class="flex gap-1">
                  <n-button size="tiny" type="success" secondary @click="confirmEvidenceReview(item, 'validated')">
                    {{ $t("page.research.validateEvidence") }}
                  </n-button>
                  <n-button size="tiny" type="error" tertiary @click="confirmEvidenceReview(item, 'rejected')">
                    {{ $t("common.reject") }}
                  </n-button>
                </div>
              </div>
            </article>
            <n-empty v-if="!bundle.evidence.length" class="py-5" :description="$t('page.research.noEvidence')" />
          </div>
        </n-tab-pane>

        <n-tab-pane name="knowledge" :tab="`${$t('page.research.knowledgeCandidates')} (${bundle.knowledge_items.length})`">
          <div class="space-y-3">
            <article v-for="item in bundle.knowledge_items" :key="item.id" class="scientific-card">
              <div class="flex flex-wrap items-center gap-2">
                <n-tag size="small" round :type="item.state === 'reviewed' ? 'success' : 'warning'">
                  {{ knowledgeStateLabel(item.state) }}
                </n-tag>
                <span class="aira-type-meta">{{ knowledgeKindLabel(item.kind) }} · r{{ item.revision }}</span>
              </div>
              <h3 class="aira-type-card-title mb-0 mt-2 break-words">
                {{ item.title }}
              </h3>
              <p class="aira-type-body line-clamp-3 mb-0 mt-2 whitespace-pre-wrap">
                {{ item.body }}
              </p>
              <div class="mt-3 flex flex-wrap items-center justify-between gap-2">
                <span class="aira-type-meta aira-text-secondary">
                  {{ $t("page.research.knowledgeEvidenceCount", { count: item.evidence.length }) }}
                </span>
                <n-button size="tiny" secondary @click="openProjectKnowledge">
                  {{ $t("page.research.openProjectKnowledge") }}
                </n-button>
              </div>
            </article>
            <n-empty v-if="!bundle.knowledge_items.length" class="py-5" :description="$t('page.research.noKnowledgeCandidates')" />
          </div>
        </n-tab-pane>

        <n-tab-pane name="data" :tab="`${$t('page.research.dataAssets')} (${bundle.data_assets.length})`">
          <div class="grid grid-cols-1 gap-3 md:grid-cols-2">
            <article v-for="asset in bundle.data_assets" :key="asset.id" class="scientific-card">
              <div class="flex items-start justify-between gap-2">
                <div class="min-w-0">
                  <div class="flex flex-wrap items-center gap-2">
                    <n-tag size="small" round :type="asset.status === 'ready' ? 'success' : 'default'">
                      {{ dataAssetStatusLabel(asset.status) }}
                    </n-tag>
                    <span class="aira-type-meta">{{ dataAssetKindLabel(asset.kind) }} · v{{ asset.current_version }}</span>
                  </div>
                  <h3 class="aira-type-card-title mb-0 mt-2 break-words">
                    {{ asset.name }}
                  </h3>
                  <p v-if="asset.description" class="aira-type-meta aira-text-secondary line-clamp-2 mb-0 mt-1">
                    {{ asset.description }}
                  </p>
                  <a
                    v-if="currentVersion(asset)?.external_uri"
                    class="aira-type-meta mt-2 block truncate text-primary"
                    :href="currentVersion(asset)?.external_uri"
                    target="_blank"
                    rel="noopener noreferrer"
                  >{{ currentVersion(asset)?.external_uri }}</a>
                </div>
                <n-button
                  v-if="asset.status === 'draft'"
                  size="tiny"
                  type="success"
                  secondary
                  @click="confirmAssetReady(asset)"
                >
                  {{ $t("page.research.markReady") }}
                </n-button>
              </div>
            </article>
          </div>
          <n-empty v-if="!bundle.data_assets.length" class="py-5" :description="$t('page.research.noDataAssets')" />
        </n-tab-pane>
      </n-tabs>
    </n-spin>

    <n-modal
      v-model:show="modalVisible"
      preset="card"
      class="research-asset-modal"
      :title="modalTitle"
      :mask-closable="false"
      @after-leave="resetModal"
    >
      <template v-if="!preview">
        <n-form v-if="modalKind === 'asset'" label-placement="top">
          <div class="grid grid-cols-1 gap-x-3 sm:grid-cols-2">
            <n-form-item :label="$t('page.research.assetName')" required>
              <n-input v-model:value="assetDraft.name" />
            </n-form-item>
            <n-form-item :label="$t('page.research.assetKind')" required>
              <n-select v-model:value="assetDraft.kind" :options="assetKindOptions" />
            </n-form-item>
          </div>
          <n-form-item :label="$t('page.research.externalUri')" required>
            <n-input v-model:value="assetDraft.external_uri" placeholder="https://…" />
          </n-form-item>
          <n-form-item :label="$t('page.research.mediaType')">
            <n-input v-model:value="assetDraft.media_type" placeholder="text/csv" />
          </n-form-item>
          <n-form-item :label="$t('common.description')">
            <n-input v-model:value="assetDraft.description" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" />
          </n-form-item>
        </n-form>

        <n-form v-else-if="modalKind === 'evidence'" label-placement="top">
          <div class="grid grid-cols-1 gap-x-3 sm:grid-cols-2">
            <n-form-item :label="$t('page.research.evidenceKind')" required>
              <n-select v-model:value="evidenceDraft.kind" :options="evidenceKindOptions" />
            </n-form-item>
            <n-form-item :label="$t('page.research.evidenceSource')" required>
              <n-select v-model:value="evidenceDraft.artifact_type" :options="evidenceSourceOptions" @update:value="resetEvidenceSource" />
            </n-form-item>
          </div>
          <n-form-item v-if="evidenceDraft.artifact_type === 'data_asset'" :label="$t('page.research.dataAsset')" required>
            <n-select v-model:value="evidenceDraft.artifact_id" :options="dataAssetOptions" />
          </n-form-item>
          <n-form-item v-else :label="$t('page.research.externalUri')" required>
            <n-input v-model:value="evidenceDraft.artifact_id" placeholder="https://…" />
          </n-form-item>
          <n-form-item :label="$t('page.research.evidenceSummary')">
            <n-input v-model:value="evidenceDraft.summary" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" />
          </n-form-item>
        </n-form>

        <n-form v-else-if="modalKind === 'claim'" label-placement="top">
          <n-form-item :label="$t('page.research.claimStatement')" required>
            <n-input v-model:value="claimDraft.statement" type="textarea" :autosize="{ minRows: 4, maxRows: 10 }" />
          </n-form-item>
          <n-form-item :label="$t('page.research.confidence')">
            <n-slider v-model:value="claimDraft.confidence" :min="0" :max="1" :step="0.05" :tooltip="true" />
          </n-form-item>
          <n-form-item :label="$t('page.research.uncertainty')">
            <n-input v-model:value="claimDraft.uncertainty" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" />
          </n-form-item>
          <n-form-item :label="$t('page.research.linkEvidence')">
            <n-select v-model:value="selectedEvidenceIds" multiple clearable :options="evidenceOptions" />
          </n-form-item>
        </n-form>

        <n-form v-else label-placement="top">
          <n-alert type="info" class="mb-4">
            {{ $t("page.research.knowledgeSuggestionBoundary") }}
          </n-alert>
          <div class="grid grid-cols-1 gap-x-3 sm:grid-cols-2">
            <n-form-item :label="$t('page.knowledge.knowledgeTitle')" required>
              <n-input v-model:value="knowledgeDraft.title" />
            </n-form-item>
            <n-form-item :label="$t('page.knowledge.kind')" required>
              <n-select v-model:value="knowledgeDraft.kind" :options="knowledgeKindOptions" />
            </n-form-item>
          </div>
          <n-form-item :label="$t('page.knowledge.knowledgeBody')" required>
            <n-input
              v-model:value="knowledgeDraft.body"
              type="textarea"
              :autosize="{ minRows: 5, maxRows: 12 }"
              :placeholder="$t('page.knowledge.knowledgeBodyPlaceholder')"
            />
          </n-form-item>
          <n-form-item :label="$t('page.research.validatedEvidence')" required>
            <n-select
              v-model:value="knowledgeDraft.evidence_ids"
              multiple
              clearable
              :options="knowledgeEvidenceOptions"
            />
          </n-form-item>
          <n-form-item :label="$t('page.knowledge.tags')">
            <n-dynamic-tags v-model:value="knowledgeDraft.tags" />
          </n-form-item>
        </n-form>
      </template>
      <template v-else>
        <n-alert type="info">
          {{ $t("page.research.assetPreviewHint") }}
        </n-alert>
        <div class="scientific-preview mt-4">
          <div class="aira-type-eyebrow">
            {{ $t("page.research.saveDestination") }}
          </div>
          <div class="aira-type-card-title mt-1">
            {{ previewDestinationLabel }}
          </div>
          <p class="aira-type-body aira-text-secondary mb-0 mt-3 whitespace-pre-wrap">
            {{ previewSummary }}
          </p>
          <div class="aira-type-meta mt-3 break-all">
            {{ $t("page.research.previewDigest") }} · {{ preview.preview_digest }}
          </div>
        </div>
      </template>
      <template #footer>
        <div class="flex justify-end gap-2">
          <n-button @click="preview ? preview = null : modalVisible = false">
            {{ preview ? $t("page.research.backToEdit") : $t("common.cancel") }}
          </n-button>
          <n-button v-if="!preview" type="primary" :disabled="!canPreview" :loading="mutating" @click="createPreview">
            {{ $t("page.research.previewAssetWrite") }}
          </n-button>
          <n-button v-else type="primary" :loading="mutating" @click="confirmCreate">
            {{ $t("page.research.confirmAssetWrite") }}
          </n-button>
        </div>
      </template>
    </n-modal>
  </section>
</template>

<script setup lang="ts">
import type {
  AssetPreview,
  ClaimDraft,
  ClaimState,
  DataAsset,
  DataAssetDraft,
  DataAssetKind,
  EvidenceArtifactType,
  EvidenceDraft,
  EvidenceKind,
  EvidenceQuality,
  KnowledgeSuggestionDraft,
  ResearchAssetBundle,
  ResearchClaim,
  ResearchEvidence,
  ResearchKnowledgeItem,
  ResearchKnowledgeKind,
} from "@/service/api/research-assets"
import type { TagProps } from "naive-ui"
import {
  createClaim,
  createDataAsset,
  createEvidence,
  createKnowledgeSuggestion,
  fetchResearchAssets,
  previewClaim,
  previewDataAsset,
  previewEvidence,
  previewKnowledgeSuggestion,
  reviewClaim,
  reviewEvidence,
  updateDataAssetStatus,
} from "@/service/api/research-assets"
import { $t } from "@airalogy/shared/locales"
import { useDialog } from "naive-ui"
import { useRouter } from "vue-router"

const props = defineProps<{
  taskId: string
  labUid: string
  projectUid: string
}>()

const emit = defineEmits<{
  changed: []
}>()

type ModalKind = "asset" | "evidence" | "claim" | "knowledge"

const emptyBundle = (): ResearchAssetBundle => ({ data_assets: [], evidence: [], claims: [], knowledge_items: [] })
const dialog = useDialog()
const router = useRouter()
const bundle = ref<ResearchAssetBundle>(emptyBundle())
const loading = ref(false)
const loadError = ref(false)
const mutating = ref(false)
const modalVisible = ref(false)
const modalKind = ref<ModalKind>("asset")
const preview = ref<AssetPreview<any> | null>(null)
const selectedEvidenceIds = ref<string[]>([])

const assetDraft = reactive<DataAssetDraft>(newAssetDraft())
const evidenceDraft = reactive<EvidenceDraft>(newEvidenceDraft())
const claimDraft = reactive<ClaimDraft>(newClaimDraft())
const knowledgeDraft = reactive<KnowledgeSuggestionDraft>(newKnowledgeDraft())

const isEmpty = computed(() => !bundle.value.data_assets.length && !bundle.value.evidence.length && !bundle.value.claims.length && !bundle.value.knowledge_items.length)
const modalTitle = computed(() => {
  const keys: Record<ModalKind, I18n.I18nKey> = {
    asset: "page.research.addDataAsset",
    evidence: "page.research.addEvidence",
    claim: "page.research.addClaim",
    knowledge: "page.research.suggestKnowledge",
  }
  return $t(keys[modalKind.value])
})
const assetKindValues: DataAssetKind[] = ["file", "table", "image", "model", "archive", "external"]
const assetKindOptions = computed(() => assetKindValues.map(value => ({ value, label: dataAssetKindLabel(value) })))
const evidenceKindValues: EvidenceKind[] = ["observation", "measurement", "analysis", "citation", "validation"]
const evidenceKindOptions = computed(() => evidenceKindValues.map(value => ({ value, label: evidenceKindLabel(value) })))
const evidenceSourceOptions = computed(() => ([
  { value: "data_asset", label: $t("page.research.dataAsset") },
  { value: "external", label: $t("page.research.externalSource") },
]))
const dataAssetOptions = computed(() => bundle.value.data_assets.map(asset => ({
  value: asset.id,
  label: `${asset.name} · v${asset.current_version}`,
})))
const evidenceOptions = computed(() => bundle.value.evidence.map(item => ({
  value: item.id,
  label: item.summary || artifactLabel(item),
})))
const knowledgeKindValues: ResearchKnowledgeKind[] = ["note", "method", "decision", "finding"]
const knowledgeKindOptions = computed(() => knowledgeKindValues.map(value => ({ value, label: knowledgeKindLabel(value) })))
const knowledgeEvidenceOptions = computed(() => bundle.value.evidence
  .filter(item => item.quality_state === "validated" && (item.artifact_type === "record" || item.artifact_type === "data_asset"))
  .map(item => ({
    value: item.id,
    label: item.summary || artifactLabel(item),
  })))
const canPreview = computed(() => {
  if (modalKind.value === "asset")
    return Boolean(assetDraft.name.trim() && assetDraft.external_uri.trim())
  if (modalKind.value === "evidence")
    return Boolean(evidenceDraft.artifact_id.trim())
  if (modalKind.value === "claim")
    return Boolean(claimDraft.statement.trim())
  return Boolean(knowledgeDraft.title.trim() && knowledgeDraft.body.trim() && knowledgeDraft.evidence_ids.length)
})
const previewSummary = computed(() => {
  if (modalKind.value === "asset")
    return `${assetDraft.name}\n${assetDraft.external_uri}`
  if (modalKind.value === "evidence")
    return evidenceDraft.summary || evidenceDraft.artifact_id
  if (modalKind.value === "claim")
    return claimDraft.statement
  return `${knowledgeDraft.title}\n${knowledgeDraft.body}`
})
const previewDestinationLabel = computed(() => preview.value?.destination.project_name || preview.value?.destination.task_title || "")

function newAssetDraft(): DataAssetDraft {
  return {
    task_id: props.taskId,
    name: "",
    description: "",
    kind: "file",
    external_uri: "",
    media_type: "",
    checksum: "",
    data_schema: {},
    metadata: {},
    source: { registered_from: "research_task_workbench" },
    change_summary: "Created from Research Task workbench",
  }
}

function newEvidenceDraft(): EvidenceDraft {
  return {
    task_id: props.taskId,
    kind: "observation",
    artifact_type: "data_asset",
    artifact_id: "",
    artifact_version: "",
    summary: "",
  }
}

function newClaimDraft(): ClaimDraft {
  return {
    task_id: props.taskId,
    statement: "",
    confidence: 0.5,
    uncertainty: "",
    evidence: [],
  }
}

function newKnowledgeDraft(): KnowledgeSuggestionDraft {
  return {
    task_id: props.taskId,
    title: "",
    body: "",
    kind: "finding",
    tags: [],
    evidence_ids: [],
  }
}

async function loadAssets() {
  loading.value = true
  loadError.value = false
  try {
    bundle.value = await fetchResearchAssets(props.taskId)
  }
  catch {
    loadError.value = true
  }
  finally {
    loading.value = false
  }
}

function openModal(kind: ModalKind) {
  modalKind.value = kind
  modalVisible.value = true
}

function openProjectKnowledge() {
  return router.push({
    name: "project-knowledge",
    params: { labUid: props.labUid, projectUid: props.projectUid },
  })
}

function resetModal() {
  preview.value = null
  selectedEvidenceIds.value = []
  Object.assign(assetDraft, newAssetDraft())
  Object.assign(evidenceDraft, newEvidenceDraft())
  Object.assign(claimDraft, newClaimDraft())
  Object.assign(knowledgeDraft, newKnowledgeDraft())
}

function resetEvidenceSource(value: EvidenceArtifactType) {
  evidenceDraft.artifact_type = value
  evidenceDraft.artifact_id = ""
  evidenceDraft.artifact_version = ""
}

function normalizedEvidenceDraft(): EvidenceDraft {
  const asset = evidenceDraft.artifact_type === "data_asset"
    ? bundle.value.data_assets.find(item => item.id === evidenceDraft.artifact_id)
    : undefined
  return {
    ...evidenceDraft,
    artifact_version: asset ? String(asset.current_version) : "",
  }
}

function normalizedClaimDraft(): ClaimDraft {
  return {
    ...claimDraft,
    evidence: selectedEvidenceIds.value.map(evidenceId => ({
      evidence_id: evidenceId,
      relation: "supports",
      rationale: "",
    })),
  }
}

async function createPreview() {
  mutating.value = true
  try {
    if (modalKind.value === "asset")
      preview.value = await previewDataAsset({ ...assetDraft })
    else if (modalKind.value === "evidence")
      preview.value = await previewEvidence(normalizedEvidenceDraft())
    else if (modalKind.value === "claim")
      preview.value = await previewClaim(normalizedClaimDraft())
    else
      preview.value = await previewKnowledgeSuggestion({ ...knowledgeDraft })
  }
  finally {
    mutating.value = false
  }
}

async function confirmCreate() {
  if (!preview.value)
    return
  mutating.value = true
  try {
    if (modalKind.value === "asset") {
      await createDataAsset({ ...assetDraft, preview_digest: preview.value.preview_digest })
    }
    else if (modalKind.value === "evidence") {
      await createEvidence({ ...normalizedEvidenceDraft(), preview_digest: preview.value.preview_digest })
    }
    else if (modalKind.value === "claim") {
      await createClaim({ ...normalizedClaimDraft(), preview_digest: preview.value.preview_digest })
    }
    else {
      await createKnowledgeSuggestion({ ...knowledgeDraft, preview_digest: preview.value.preview_digest })
    }
    modalVisible.value = false
    window.$message?.success($t("page.research.assetWriteCompleted"))
    await loadAssets()
    emit("changed")
  }
  finally {
    mutating.value = false
  }
}

function confirmAssetReady(asset: DataAsset) {
  dialog.success({
    title: $t("page.research.markReady"),
    content: $t("page.research.markReadyConfirm"),
    positiveText: $t("common.confirm"),
    negativeText: $t("common.cancel"),
    onPositiveClick: async () => {
      await updateDataAssetStatus(asset, "ready")
      await loadAssets()
      emit("changed")
    },
  })
}

function confirmEvidenceReview(item: ResearchEvidence, state: "validated" | "rejected") {
  dialog.warning({
    title: state === "validated" ? $t("page.research.validateEvidence") : $t("page.research.rejectEvidence"),
    content: $t("page.research.evidenceReviewConfirm"),
    positiveText: $t("common.confirm"),
    negativeText: $t("common.cancel"),
    onPositiveClick: async () => {
      await reviewEvidence(item, state)
      await loadAssets()
      emit("changed")
    },
  })
}

function confirmClaimReview(item: ResearchClaim, state: "reviewed" | "rejected") {
  dialog.warning({
    title: state === "reviewed" ? $t("page.research.acceptClaim") : $t("page.research.rejectClaim"),
    content: $t("page.research.claimReviewConfirm"),
    positiveText: $t("common.confirm"),
    negativeText: $t("common.cancel"),
    onPositiveClick: async () => {
      await reviewClaim(item, state)
      await loadAssets()
      emit("changed")
    },
  })
}

function currentVersion(asset: DataAsset) {
  return asset.versions.find(version => version.version === asset.current_version)
}

function artifactLabel(item: ResearchEvidence) {
  return `${artifactTypeLabel(item.artifact_type)} · ${item.artifact_id}${item.artifact_version ? ` · v${item.artifact_version}` : ""}`
}

function claimStateType(state: ClaimState): TagProps["type"] {
  if (state === "reviewed")
    return "success"
  if (state === "rejected")
    return "error"
  return "warning"
}

function evidenceStateType(state: EvidenceQuality): TagProps["type"] {
  if (state === "validated")
    return "success"
  if (state === "rejected")
    return "error"
  return "warning"
}

function claimStateLabel(value: ClaimState) {
  return $t(`page.research.claimState.${value}` as I18n.I18nKey)
}

function evidenceStateLabel(value: EvidenceQuality) {
  return $t(`page.research.evidenceQuality.${value}` as I18n.I18nKey)
}

function evidenceKindLabel(value: EvidenceKind) {
  return $t(`page.research.evidenceKindValue.${value}` as I18n.I18nKey)
}

function artifactTypeLabel(value: EvidenceArtifactType) {
  return $t(`page.research.artifactType.${value}` as I18n.I18nKey)
}

function dataAssetKindLabel(value: DataAssetKind) {
  return $t(`page.research.dataAssetKind.${value}` as I18n.I18nKey)
}

function dataAssetStatusLabel(value: DataAsset["status"]) {
  return $t(`page.research.dataAssetStatus.${value}` as I18n.I18nKey)
}

function knowledgeKindLabel(value: ResearchKnowledgeKind) {
  const keys: Record<ResearchKnowledgeKind, I18n.I18nKey> = {
    note: "page.knowledge.kindNote",
    method: "page.knowledge.kindMethod",
    decision: "page.knowledge.kindDecision",
    finding: "page.knowledge.kindFinding",
  }
  return $t(keys[value])
}

function knowledgeStateLabel(value: ResearchKnowledgeItem["state"]) {
  const keys: Record<ResearchKnowledgeItem["state"], I18n.I18nKey> = {
    suggested: "page.knowledge.stateSuggested",
    draft: "page.knowledge.stateDraft",
    reviewed: "page.knowledge.stateReviewed",
    superseded: "page.knowledge.stateSuperseded",
    archived: "page.knowledge.stateArchived",
  }
  return $t(keys[value])
}

onMounted(loadAssets)
watch(() => props.taskId, () => {
  resetModal()
  loadAssets()
})
</script>

<style scoped>
.research-assets-panel {
  border: 1px solid rgb(229 231 235);
  border-radius: 0.875rem;
  background: white;
  padding: 1.25rem;
}

.scientific-card,
.scientific-preview {
  border: 1px solid rgb(226 232 240);
  border-radius: 0.75rem;
  background: rgb(248 250 252 / 72%);
  padding: 1rem;
}

.research-asset-modal {
  width: min(42rem, calc(100vw - 2rem));
}
</style>
