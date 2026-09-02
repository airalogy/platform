<template>
  <n-button type="primary" @click="openModal">
    <template #icon>
      <n-icon><icon-tabler-file-upload /></n-icon>
    </template>
    {{ $t("page.knowledge.importPaper") }}
  </n-button>

  <n-modal
    v-model:show="visible"
    preset="card"
    class="knowledge-modal"
    :title="$t('page.knowledge.importPaper')"
    :mask-closable="false"
    @after-leave="reset"
  >
    <template v-if="!preview">
      <n-form label-placement="top">
        <div class="grid grid-cols-1 gap-4 md:grid-cols-2">
          <n-form-item :label="$t('page.knowledge.sourceType')" required>
            <n-select v-model:value="sourceType" :options="sourceOptions" />
          </n-form-item>
          <n-form-item :label="$t('page.knowledge.visibility')" required>
            <n-select v-model:value="visibility" :options="visibilityOptions" />
          </n-form-item>
        </div>

        <n-form-item v-if="sourceType === 'pdf'" :label="$t('page.knowledge.selectPdf')" required>
          <n-upload
            accept="application/pdf,.pdf"
            :max="1"
            :default-upload="false"
            @change="handleFileChange"
          >
            <n-upload-dragger>
              <div class="py-3">
                <n-icon :size="36">
                  <icon-tabler-file-type-pdf />
                </n-icon>
                <p class="aira-type-body mb-0 mt-2">
                  {{ selectedFile?.name || $t("page.knowledge.selectPdf") }}
                </p>
                <p class="aira-type-meta aira-text-muted mb-0 mt-1">
                  {{ $t("page.knowledge.pdfRequirements") }}
                </p>
              </div>
            </n-upload-dragger>
          </n-upload>
        </n-form-item>

        <n-form-item
          v-else-if="sourceType !== 'manual'"
          :label="$t('page.knowledge.source')"
          required
        >
          <n-input
            v-model:value="source"
            :type="sourceType === 'bibtex' || sourceType === 'ris' ? 'textarea' : 'text'"
            :autosize="{ minRows: 4, maxRows: 10 }"
          />
        </n-form-item>

        <n-form-item
          :label="$t('page.knowledge.paperTitle')"
          :required="sourceType === 'manual' || sourceType === 'pdf' || sourceType === 'url'"
        >
          <n-input v-model:value="metadata.title" :placeholder="$t('page.knowledge.paperTitlePlaceholder')" />
          <template v-if="sourceType === 'doi'" #feedback>
            {{ $t("page.knowledge.providerUnavailable") }}
          </template>
        </n-form-item>

        <div class="grid grid-cols-1 gap-4 md:grid-cols-2">
          <n-form-item :label="$t('page.knowledge.doi')">
            <n-input v-model:value="metadata.doi" :disabled="sourceType === 'doi'" />
          </n-form-item>
          <n-form-item :label="$t('page.knowledge.year')">
            <n-input-number v-model:value="metadata.publicationYear" class="w-full" :min="1000" :max="9999" />
          </n-form-item>
        </div>
        <div class="grid grid-cols-1 gap-4 md:grid-cols-2">
          <n-form-item :label="$t('page.knowledge.authors')">
            <n-input
              v-model:value="metadata.authors"
              type="textarea"
              :autosize="{ minRows: 2, maxRows: 5 }"
              :placeholder="$t('page.knowledge.authorsPlaceholder')"
            />
          </n-form-item>
          <n-form-item :label="$t('page.knowledge.venue')">
            <n-input v-model:value="metadata.venue" />
          </n-form-item>
        </div>
        <n-form-item :label="$t('page.knowledge.abstract')">
          <n-input v-model:value="metadata.abstract" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" />
        </n-form-item>
      </n-form>
    </template>

    <template v-else>
      <div class="space-y-4">
        <section class="knowledge-preview-card">
          <div class="aira-type-eyebrow">
            {{ $t("page.knowledge.importDestination") }}
          </div>
          <div class="aira-type-card-title mt-2">
            {{ props.scopeLabel }}
          </div>
          <n-tag class="mt-2" size="small" :type="preview.impact.visibility === 'restricted' ? 'warning' : 'info'">
            {{ visibilityLabel(preview.impact.visibility) }}
          </n-tag>
        </section>
        <section class="knowledge-preview-card">
          <div class="aira-type-eyebrow">
            {{ $t("page.knowledge.metadata") }}
          </div>
          <h3 class="aira-type-card-title mb-0 mt-2">
            {{ preview.paper.title }}
          </h3>
          <p class="aira-type-meta aira-text-secondary mb-0 mt-2">
            {{ [preview.paper.first_author, preview.paper.publication_year, preview.paper.venue].filter(Boolean).join(" · ") }}
          </p>
          <p v-if="preview.paper.doi" class="aira-type-meta aira-text-muted mb-0 mt-1">
            DOI · {{ preview.paper.doi }}
          </p>
        </section>
        <n-alert
          :type="preview.duplicate.kind === 'none' ? 'success' : 'warning'"
          :title="$t('page.knowledge.duplicateCheck')"
        >
          {{ duplicateMessage }}
        </n-alert>

        <template v-if="preview.duplicate.kind === 'candidate_conflict'">
          <n-radio-group v-model:value="duplicateChoice" class="w-full">
            <n-space vertical>
              <n-radio value="existing">
                {{ $t("page.knowledge.useExisting") }}
              </n-radio>
              <n-select
                v-if="duplicateChoice === 'existing'"
                v-model:value="existingPaperId"
                class="ml-6 w-[min(32rem,calc(100vw-6rem))]"
                :options="candidateOptions"
              />
              <n-radio value="distinct">
                {{ $t("page.knowledge.createDistinct") }}
              </n-radio>
            </n-space>
          </n-radio-group>
        </template>
      </div>
    </template>

    <template #footer>
      <div class="flex flex-wrap justify-end gap-2">
        <n-button @click="preview ? clearPreview() : closeModal()">
          {{ preview ? $t("page.knowledge.backToEdit") : $t("common.cancel") }}
        </n-button>
        <n-button
          v-if="!preview"
          type="primary"
          :disabled="!canPreview"
          :loading="submitting"
          @click="handlePreview"
        >
          {{ $t("page.knowledge.previewImport") }}
        </n-button>
        <n-button
          v-else
          type="primary"
          :disabled="!canConfirm"
          :loading="submitting"
          @click="handleConfirm"
        >
          {{ $t("page.knowledge.confirmImport") }}
        </n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import type {
  KnowledgeScope,
  KnowledgeVisibility,
  PaperImportPreview,
  PaperImportSource,
  PaperLibraryEntry,
} from "@/service/api/knowledge"
import type { UploadFileInfo } from "naive-ui"
import { confirmPaperImport, previewPaperImport, previewPdfImport } from "@/service/api/knowledge"
import { $t } from "@airalogy/shared/locales"

interface Props {
  scope: KnowledgeScope
  scopeLabel: string
}

const props = defineProps<Props>()
const emit = defineEmits<{ imported: [entry: PaperLibraryEntry] }>()

type ImportSource = PaperImportSource | "pdf"

const visible = ref(false)
const submitting = ref(false)
const sourceType = ref<ImportSource>("doi")
const visibility = ref<KnowledgeVisibility>(props.scope.visibility)
const source = ref("")
const selectedFile = ref<File | null>(null)
const preview = ref<PaperImportPreview | null>(null)
const duplicateChoice = ref<"existing" | "distinct">("existing")
const existingPaperId = ref<string | null>(null)
const metadata = reactive({
  title: "",
  doi: "",
  authors: "",
  publicationYear: null as number | null,
  venue: "",
  abstract: "",
})

const sourceOptions = computed(() => [
  { label: $t("page.knowledge.sourceDoi"), value: "doi" },
  { label: $t("page.knowledge.sourcePdf"), value: "pdf" },
  { label: $t("page.knowledge.sourceUrl"), value: "url" },
  { label: $t("page.knowledge.sourceBibtex"), value: "bibtex" },
  { label: $t("page.knowledge.sourceRis"), value: "ris" },
  { label: $t("page.knowledge.sourceManual"), value: "manual" },
])
const visibilityOptions = computed(() => {
  const normal = props.scope.scope_type === "personal"
    ? { label: $t("page.knowledge.visibilityPrivate"), value: "private" }
    : props.scope.scope_type === "lab"
      ? { label: $t("page.knowledge.visibilityLab"), value: "lab" }
      : { label: $t("page.knowledge.visibilityProject"), value: "project" }
  return [normal, { label: $t("page.knowledge.visibilityRestricted"), value: "restricted" }]
})
const canPreview = computed(() => {
  if (sourceType.value === "pdf")
    return Boolean(selectedFile.value && metadata.title.trim())
  if (sourceType.value === "manual")
    return Boolean(metadata.title.trim())
  if (sourceType.value === "doi")
    return Boolean(source.value.trim())
  return Boolean(source.value.trim() && (sourceType.value !== "url" || metadata.title.trim()))
})
const canConfirm = computed(() => {
  if (!preview.value)
    return false
  if (preview.value.duplicate.kind !== "candidate_conflict")
    return true
  return duplicateChoice.value === "distinct" || Boolean(existingPaperId.value)
})
const duplicateMessage = computed(() => {
  if (preview.value?.duplicate.kind === "exact_doi")
    return $t("page.knowledge.exactDoi")
  if (preview.value?.duplicate.kind === "candidate_conflict")
    return $t("page.knowledge.candidateConflict")
  return $t("page.knowledge.noDuplicate")
})
const candidateOptions = computed(() => preview.value?.duplicate.candidates.map(candidate => ({
  label: [candidate.title, candidate.first_author, candidate.publication_year].filter(Boolean).join(" · "),
  value: candidate.id,
})) || [])

watch(() => props.scope, (scope) => {
  visibility.value = scope.visibility
  clearPreview()
}, { deep: true })

watch(sourceType, () => {
  clearPreview()
  selectedFile.value = null
  source.value = ""
})

function visibilityLabel(value: KnowledgeVisibility) {
  const key = value === "private"
    ? "visibilityPrivate"
    : value === "lab"
      ? "visibilityLab"
      : value === "project"
        ? "visibilityProject"
        : "visibilityRestricted"
  return $t(`page.knowledge.${key}` as I18n.I18nKey)
}

function authors() {
  return metadata.authors.split("\n").map(value => value.trim()).filter(Boolean)
}

function metadataPayload() {
  return {
    title: metadata.title.trim(),
    doi: sourceType.value === "doi" ? undefined : metadata.doi.trim() || undefined,
    authors: authors(),
    publication_year: metadata.publicationYear || undefined,
    venue: metadata.venue.trim(),
    abstract: metadata.abstract.trim(),
  }
}

function handleFileChange(options: { file: UploadFileInfo }) {
  selectedFile.value = options.file.file || null
  if (selectedFile.value && !metadata.title)
    metadata.title = selectedFile.value.name.replace(/\.pdf$/i, "")
}

function openModal() {
  visibility.value = props.scope.visibility
  visible.value = true
}

function closeModal() {
  visible.value = false
}

function clearPreview() {
  preview.value = null
  duplicateChoice.value = "existing"
  existingPaperId.value = null
}

function reset() {
  clearPreview()
  sourceType.value = "doi"
  source.value = ""
  selectedFile.value = null
  Object.assign(metadata, {
    title: "",
    doi: "",
    authors: "",
    publicationYear: null,
    venue: "",
    abstract: "",
  })
}

async function handlePreview() {
  if (!canPreview.value)
    return
  submitting.value = true
  try {
    if (sourceType.value === "pdf" && selectedFile.value) {
      preview.value = await previewPdfImport({
        ...props.scope,
        visibility: visibility.value,
        file: selectedFile.value,
        title: metadata.title.trim(),
        doi: metadata.doi.trim() || undefined,
        authors: authors(),
        publication_year: metadata.publicationYear,
        venue: metadata.venue.trim(),
        abstract: metadata.abstract.trim(),
      })
    }
    else if (sourceType.value !== "pdf") {
      preview.value = await previewPaperImport({
        ...props.scope,
        visibility: visibility.value,
        source_type: sourceType.value,
        source: source.value.trim(),
        metadata: metadataPayload(),
      })
    }
    existingPaperId.value = preview.value?.duplicate.candidate_ids[0] || null
  }
  finally {
    submitting.value = false
  }
}

async function handleConfirm() {
  if (!preview.value || !canConfirm.value)
    return
  submitting.value = true
  try {
    const exactDoi = preview.value.duplicate.kind === "exact_doi"
    const useExisting = exactDoi || (
      preview.value.duplicate.kind === "candidate_conflict" && duplicateChoice.value === "existing"
    )
    const entry = await confirmPaperImport(preview.value.id, {
      preview_digest: preview.value.preview_digest,
      duplicate_resolution: useExisting ? "use_existing" : "create_new",
      existing_paper_id: useExisting && !exactDoi ? existingPaperId.value || undefined : undefined,
      confirm_distinct: duplicateChoice.value === "distinct",
    })
    window.$message?.success($t("page.knowledge.imported"))
    emit("imported", entry)
    visible.value = false
  }
  finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.knowledge-modal {
  width: min(50rem, calc(100vw - 2rem));
}

.knowledge-preview-card {
  border: 1px solid rgb(229 231 235);
  border-radius: 0.75rem;
  background: rgb(249 250 251);
  padding: 1rem;
}
</style>
