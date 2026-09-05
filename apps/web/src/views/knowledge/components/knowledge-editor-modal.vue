<template>
  <n-button @click="open()">
    <template #icon>
      <n-icon><icon-tabler-notes /></n-icon>
    </template>
    {{ $t("page.knowledge.newKnowledge") }}
  </n-button>

  <n-modal
    v-model:show="visible"
    preset="card"
    class="knowledge-editor-modal"
    :title="editing ? $t('page.knowledge.editKnowledge') : $t('page.knowledge.createKnowledge')"
    :mask-closable="false"
  >
    <n-alert type="info" class="mb-4">
      {{ props.scopeLabel }} · {{ $t(props.scope.scope_type === 'personal' ? "page.knowledge.personalDraftHint" : "page.knowledge.reviewHint") }}
    </n-alert>
    <n-alert v-if="saveError" type="error" class="mb-4" role="alert" data-testid="knowledge-save-error">
      {{ $t("page.knowledge.saveFailedHint") }}
    </n-alert>
    <n-form label-placement="top">
      <div class="grid grid-cols-1 gap-4 md:grid-cols-2">
        <n-form-item :label="$t('page.knowledge.kind')" required>
          <n-select v-model:value="form.kind" :options="kindOptions" />
        </n-form-item>
        <n-form-item :label="$t('page.knowledge.visibility')" required>
          <n-select v-model:value="form.visibility" :options="visibilityOptions" :disabled="Boolean(editing)" />
        </n-form-item>
      </div>
      <n-form-item :label="$t('page.knowledge.knowledgeTitle')" required>
        <n-input v-model:value="form.title" data-testid="knowledge-title" />
      </n-form-item>
      <n-form-item :label="$t('page.knowledge.knowledgeBody')" required>
        <n-input
          v-model:value="form.body"
          type="textarea"
          :autosize="{ minRows: 8, maxRows: 18 }"
          :placeholder="$t('page.knowledge.knowledgeBodyPlaceholder')"
          data-testid="knowledge-body"
        />
      </n-form-item>
      <n-form-item :label="$t('page.knowledge.tags')">
        <n-dynamic-tags v-model:value="form.tags" />
      </n-form-item>
      <n-form-item v-if="editing" :label="$t('page.knowledge.changeSummary')">
        <n-input v-model:value="form.changeSummary" />
      </n-form-item>
      <n-alert v-if="linkedPaperTitle" type="success">
        {{ $t("page.knowledge.createFromPaper") }} · {{ linkedPaperTitle }}
      </n-alert>
      <n-alert
        v-if="airaDraft"
        type="info"
        class="mt-3"
        :title="$t('page.knowledge.airaSuggested')"
      >
        <p class="mb-0">
          {{ $t(
            props.scope.scope_type === "personal"
              ? "page.knowledge.airaPersonalDraftHint"
              : "page.knowledge.airaSuggestedHint",
          ) }}
        </p>
        <p class="mb-0 mt-2">
          {{ airaDraft.rationale }}
        </p>
        <ul v-if="airaDraft.assumptions.length || airaDraft.warnings.length" class="mb-0 mt-2 pl-5">
          <li v-for="item in [...airaDraft.assumptions, ...airaDraft.warnings]" :key="item">
            {{ item }}
          </li>
        </ul>
      </n-alert>
    </n-form>

    <template #footer>
      <div class="flex justify-end gap-2">
        <n-button @click="visible = false">
          {{ $t("common.cancel") }}
        </n-button>
        <n-button
          type="primary"
          :disabled="!isValid"
          :loading="saving"
          data-testid="knowledge-create-confirm"
          @click="save"
        >
          {{ editing ? $t("common.save") : $t("page.knowledge.createKnowledge") }}
        </n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import type {
  AiraPaperKnowledgeDraft,
  KnowledgeItem,
  KnowledgeKind,
  KnowledgeScope,
  KnowledgeVisibility,
} from "@/service/api/knowledge"
import {
  createKnowledgeItem,
  previewKnowledgeItem,
  updateKnowledgeItem,
} from "@/service/api/knowledge"
import { $t } from "@airalogy/shared/locales"

interface Props {
  scope: KnowledgeScope
  scopeLabel: string
}

interface OpenOptions {
  item?: KnowledgeItem
  paperId?: string
  paperTitle?: string
  restrictedSource?: boolean
  airaDraft?: AiraPaperKnowledgeDraft
}

const props = defineProps<Props>()
const emit = defineEmits<{ saved: [item: KnowledgeItem] }>()

const visible = ref(false)
const saving = ref(false)
const saveError = ref(false)
const editing = ref<KnowledgeItem | null>(null)
const linkedPaperId = ref("")
const linkedPaperTitle = ref("")
const airaDraft = ref<AiraPaperKnowledgeDraft | null>(null)
const form = reactive({
  kind: "note" as KnowledgeKind,
  visibility: props.scope.visibility as KnowledgeVisibility,
  title: "",
  body: "",
  tags: [] as string[],
  changeSummary: "",
})

const kindOptions = computed(() => [
  { label: $t("page.knowledge.kindReference"), value: "reference" },
  { label: $t("page.knowledge.kindNote"), value: "note" },
  { label: $t("page.knowledge.kindMethod"), value: "method" },
  { label: $t("page.knowledge.kindDecision"), value: "decision" },
  { label: $t("page.knowledge.kindFinding"), value: "finding" },
])
const visibilityOptions = computed(() => {
  const normal = props.scope.scope_type === "personal"
    ? { label: $t("page.knowledge.visibilityPrivate"), value: "private" }
    : props.scope.scope_type === "lab"
      ? { label: $t("page.knowledge.visibilityLab"), value: "lab" }
      : { label: $t("page.knowledge.visibilityProject"), value: "project" }
  return [normal, { label: $t("page.knowledge.visibilityRestricted"), value: "restricted" }]
})
const isValid = computed(() => Boolean(form.title.trim() && form.body.trim()))

watch(() => props.scope, () => {
  if (!visible.value)
    form.visibility = props.scope.visibility
}, { deep: true })

function reset() {
  saveError.value = false
  editing.value = null
  linkedPaperId.value = ""
  linkedPaperTitle.value = ""
  airaDraft.value = null
  Object.assign(form, {
    kind: "note",
    visibility: props.scope.visibility,
    title: "",
    body: "",
    tags: [],
    changeSummary: "",
  })
}

function open(options: OpenOptions = {}) {
  reset()
  if (options.item) {
    editing.value = options.item
    Object.assign(form, {
      kind: options.item.kind,
      visibility: options.item.visibility,
      title: options.item.title,
      body: options.item.body,
      tags: [...options.item.tags],
    })
  }
  else if (options.paperId) {
    linkedPaperId.value = options.paperId
    linkedPaperTitle.value = options.paperTitle || ""
    airaDraft.value = options.airaDraft || null
    form.visibility = options.restrictedSource
      ? "restricted"
      : props.scope.visibility
    form.kind = options.airaDraft?.draft.kind || "reference"
    form.title = options.airaDraft?.draft.title || options.paperTitle || ""
    form.body = options.airaDraft?.draft.body || ""
    form.tags = [...(options.airaDraft?.draft.tags || [])]
  }
  visible.value = true
}

async function save() {
  if (!isValid.value)
    return
  saving.value = true
  saveError.value = false
  try {
    let item: KnowledgeItem
    if (editing.value) {
      item = await updateKnowledgeItem(editing.value.id, {
        expected_revision: editing.value.revision,
        title: form.title.trim(),
        body: form.body.trim(),
        kind: form.kind,
        tags: form.tags,
        change_summary: form.changeSummary.trim(),
      })
    }
    else {
      const payload = {
        ...props.scope,
        visibility: form.visibility,
        kind: form.kind,
        title: form.title.trim(),
        body: form.body.trim(),
        tags: form.tags,
        paper_library_entry_ids: linkedPaperId.value ? [linkedPaperId.value] : [],
        aira_generation: airaDraft.value?.aira_generation,
        aira_receipt: airaDraft.value?.aira_receipt,
      }
      const preview = await previewKnowledgeItem(payload)
      item = await createKnowledgeItem({
        ...payload,
        preview_digest: preview.preview_digest,
      })
    }
    window.$message?.success(
      editing.value ? $t("page.knowledge.updated") : $t("page.knowledge.created"),
    )
    emit("saved", item)
    visible.value = false
  }
  catch {
    saveError.value = true
  }
  finally {
    saving.value = false
  }
}

defineExpose({ open })
</script>

<style scoped>
.knowledge-editor-modal {
  width: min(48rem, calc(100vw - 2rem));
}
</style>
