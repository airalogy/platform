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
      {{ props.scopeLabel }} · {{ $t("page.knowledge.reviewHint") }}
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
        <n-input v-model:value="form.title" />
      </n-form-item>
      <n-form-item :label="$t('page.knowledge.knowledgeBody')" required>
        <n-input
          v-model:value="form.body"
          type="textarea"
          :autosize="{ minRows: 8, maxRows: 18 }"
          :placeholder="$t('page.knowledge.knowledgeBodyPlaceholder')"
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
    </n-form>

    <template #footer>
      <div class="flex justify-end gap-2">
        <n-button @click="visible = false">
          {{ $t("common.cancel") }}
        </n-button>
        <n-button type="primary" :disabled="!isValid" :loading="saving" @click="save">
          {{ editing ? $t("common.save") : $t("page.knowledge.createKnowledge") }}
        </n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import type {
  KnowledgeItem,
  KnowledgeKind,
  KnowledgeScope,
  KnowledgeVisibility,
} from "@/service/api/knowledge"
import { createKnowledgeItem, updateKnowledgeItem } from "@/service/api/knowledge"
import { $t } from "@airalogy/shared/locales"

interface Props {
  scope: KnowledgeScope
  scopeLabel: string
}

interface OpenOptions {
  item?: KnowledgeItem
  paperId?: string
  paperTitle?: string
}

const props = defineProps<Props>()
const emit = defineEmits<{ saved: [item: KnowledgeItem] }>()

const visible = ref(false)
const saving = ref(false)
const editing = ref<KnowledgeItem | null>(null)
const linkedPaperId = ref("")
const linkedPaperTitle = ref("")
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
  editing.value = null
  linkedPaperId.value = ""
  linkedPaperTitle.value = ""
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
    form.kind = "reference"
    form.title = options.paperTitle || ""
  }
  visible.value = true
}

async function save() {
  if (!isValid.value)
    return
  saving.value = true
  try {
    const item = editing.value
      ? await updateKnowledgeItem(editing.value.id, {
        expected_revision: editing.value.revision,
        title: form.title.trim(),
        body: form.body.trim(),
        kind: form.kind,
        tags: form.tags,
        change_summary: form.changeSummary.trim(),
      })
      : await createKnowledgeItem({
        ...props.scope,
        visibility: form.visibility,
        kind: form.kind,
        title: form.title.trim(),
        body: form.body.trim(),
        tags: form.tags,
        paper_library_entry_ids: linkedPaperId.value ? [linkedPaperId.value] : [],
      })
    window.$message?.success(
      editing.value ? $t("page.knowledge.updated") : $t("page.knowledge.created"),
    )
    emit("saved", item)
    visible.value = false
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
