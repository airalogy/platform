<template>
  <n-button type="primary" @click="open()">
    <template #icon><n-icon><icon-tabler-pencil-plus /></n-icon></template>
    {{ $t("page.recordDiary.newLog") }}
  </n-button>

  <n-modal
    style="--aira-dialog-width: 52rem"
    v-model:show="visible"
    preset="card"
    class="aira-dialog research-log-modal"
    :title="editing ? $t('page.recordDiary.editLog') : $t('page.recordDiary.newLog')"
    :mask-closable="false"
    :closable="!saving"
    :close-on-esc="!saving"
    @after-leave="reset"
  >
    <operation-feedback v-if="saveError" class="mb-4" uncertain data-testid="log-save-error" />
    <template v-if="!previewing">
      <n-form label-placement="top">
        <div class="grid grid-cols-1 gap-4 md:grid-cols-2">
          <n-form-item :label="$t('page.recordDiary.logScope')">
            <n-input :value="scopeLabel" disabled />
          </n-form-item>
          <n-form-item :label="$t('page.recordDiary.logKind')" required>
            <n-select v-model:value="form.kind" :options="kindOptions" />
          </n-form-item>
        </div>
        <n-form-item :label="$t('page.recordDiary.logTitle')" required>
          <n-input v-model:value="form.title" />
        </n-form-item>
        <n-form-item :label="$t('page.recordDiary.logBody')">
          <n-input v-model:value="form.body" type="textarea" :autosize="{ minRows: 4, maxRows: 12 }" />
        </n-form-item>
        <n-form-item :label="$t('page.recordDiary.logGoal')">
          <n-input v-model:value="form.goal" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" />
        </n-form-item>
        <div class="grid grid-cols-1 gap-4 md:grid-cols-2">
          <n-form-item :label="$t('page.recordDiary.completedItems')">
            <n-input v-model:value="completedText" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :placeholder="$t('page.recordDiary.onePerLine')" />
          </n-form-item>
          <n-form-item :label="$t('page.recordDiary.evidence')">
            <n-input v-model:value="evidenceText" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :placeholder="$t('page.recordDiary.onePerLine')" />
          </n-form-item>
          <n-form-item :label="$t('page.recordDiary.risks')">
            <n-input v-model:value="risksText" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :placeholder="$t('page.recordDiary.onePerLine')" />
          </n-form-item>
          <n-form-item :label="$t('page.recordDiary.nextSteps')">
            <n-input v-model:value="nextStepsText" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :placeholder="$t('page.recordDiary.onePerLine')" />
          </n-form-item>
        </div>
        <n-form-item :label="$t('page.recordDiary.assetLinks')">
          <div class="w-full flex flex-col gap-2">
            <div v-for="(asset, index) in assetLinks" :key="index" class="research-log-asset-row">
              <n-select v-model:value="asset.asset_type" :options="assetTypeOptions" />
              <n-input v-model:value="asset.asset_id" :placeholder="$t('page.recordDiary.assetId')" />
              <n-input v-model:value="asset.label" :placeholder="$t('page.recordDiary.assetLabel')" />
              <n-button quaternary type="error" @click="assetLinks.splice(index, 1)">
                <template #icon><n-icon><icon-tabler-trash /></n-icon></template>
              </n-button>
            </div>
            <n-button dashed @click="addAssetLink">
              <template #icon><n-icon><icon-tabler-link-plus /></n-icon></template>
              {{ $t("page.recordDiary.addAssetLink") }}
            </n-button>
          </div>
        </n-form-item>
        <n-form-item v-if="editing" :label="$t('page.recordDiary.changeSummary')" required>
          <n-input v-model:value="changeSummary" />
        </n-form-item>
      </n-form>
    </template>

    <template v-else>
      <n-alert type="info" class="mb-4">{{ $t("page.recordDiary.logPreviewHint") }}</n-alert>
      <section class="research-log-preview">
        <div class="aira-type-eyebrow">{{ scopeLabel }} · {{ kindLabel(form.kind) }}</div>
        <h3 class="aira-type-card-title mb-0 mt-2">{{ form.title }}</h3>
        <p v-if="form.body" class="aira-type-body aira-text-secondary mb-0 mt-3 whitespace-pre-wrap">
          {{ form.body }}
        </p>
        <div class="aira-type-meta mt-4 flex flex-wrap gap-4">
          <span>{{ $t("page.recordDiary.completedItems") }} · {{ lines(completedText).length }}</span>
          <span>{{ $t("page.recordDiary.evidence") }} · {{ lines(evidenceText).length }}</span>
          <span>{{ $t("page.recordDiary.risks") }} · {{ lines(risksText).length }}</span>
          <span>{{ $t("page.recordDiary.nextSteps") }} · {{ lines(nextStepsText).length }}</span>
          <span>{{ $t("page.recordDiary.assetLinks") }} · {{ validAssetLinks.length }}</span>
        </div>
      </section>
    </template>

    <template #footer>
      <div class="flex justify-end gap-2">
        <n-button :disabled="saving" @click="previewing ? previewing = false : (visible = false)">
          {{ previewing ? $t("page.research.backToEdit") : $t("common.cancel") }}
        </n-button>
        <n-button v-if="!previewing" type="primary" :disabled="!isValid" @click="previewing = true">
          {{ $t("page.recordDiary.previewLog") }}
        </n-button>
        <n-button v-else type="primary" :loading="saving" @click="save">
          {{ editing ? $t("common.save") : $t("page.recordDiary.confirmLog") }}
        </n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import type {
  ResearchLogAssetLink,
  ResearchLogDraft,
  ResearchLogKind,
  ResearchLogManualEntry,
  ResearchLogScopeParams,
} from "@/service/api/research-log"
import { createResearchLogEntry, updateResearchLogEntry } from "@/service/api/research-log"
import { $t } from "@airalogy/shared/locales"

const props = defineProps<{
  scope: ResearchLogScopeParams
  scopeLabel: string
}>()
const emit = defineEmits<{ saved: [entry: ResearchLogManualEntry] }>()

const visible = ref(false)
const previewing = ref(false)
const saving = ref(false)
const saveError = ref(false)
const editing = ref<ResearchLogManualEntry | null>(null)
const completedText = ref("")
const evidenceText = ref("")
const risksText = ref("")
const nextStepsText = ref("")
const assetLinks = ref<ResearchLogAssetLink[]>([])
const changeSummary = ref("")
const form = reactive({
  kind: "progress" as ResearchLogKind,
  title: "",
  body: "",
  goal: "",
})

const kindOptions = computed(() => ([
  "progress",
  "meeting",
  "reflection",
  "blocker",
  "milestone",
] as ResearchLogKind[]).map(value => ({ label: kindLabel(value), value })))
const assetTypeOptions = computed(() => ([
  "paper",
  "protocol",
  "record",
  "knowledge",
  "research_task",
  "data_asset",
  "external",
] as ResearchLogAssetLink["asset_type"][]).map(value => ({
  value,
  label: $t(`page.recordDiary.assetType.${value}` as I18n.I18nKey),
})))
const validAssetLinks = computed(() => assetLinks.value
  .filter(item => item.asset_id.trim())
  .map(item => ({ ...item, asset_id: item.asset_id.trim(), label: item.label?.trim() })))
const isValid = computed(() => Boolean(
  form.title.trim() && (!editing.value || changeSummary.value.trim()),
))

function kindLabel(kind: ResearchLogKind) {
  const suffix = kind.charAt(0).toUpperCase() + kind.slice(1)
  return $t(`page.recordDiary.kind${suffix}` as I18n.I18nKey)
}

function lines(value: string) {
  return value.split("\n").map(item => item.trim()).filter(Boolean)
}

function reset() {
  saveError.value = false
  previewing.value = false
  editing.value = null
  Object.assign(form, { kind: "progress", title: "", body: "", goal: "" })
  completedText.value = ""
  evidenceText.value = ""
  risksText.value = ""
  nextStepsText.value = ""
  assetLinks.value = []
  changeSummary.value = ""
}

function open(item?: ResearchLogManualEntry) {
  reset()
  if (item) {
    editing.value = item
    Object.assign(form, {
      kind: item.kind,
      title: item.title,
      body: item.body,
      goal: item.goal,
    })
    completedText.value = item.completed_items.join("\n")
    evidenceText.value = item.evidence.join("\n")
    risksText.value = item.risks.join("\n")
    nextStepsText.value = item.next_steps.join("\n")
    assetLinks.value = item.asset_links.map(asset => ({ ...asset }))
  }
  visible.value = true
}

function payload(): ResearchLogDraft {
  return {
    ...props.scope,
    kind: form.kind,
    title: form.title.trim(),
    body: form.body.trim(),
    goal: form.goal.trim(),
    completed_items: lines(completedText.value),
    evidence: lines(evidenceText.value),
    risks: lines(risksText.value),
    next_steps: lines(nextStepsText.value),
    asset_links: validAssetLinks.value,
  }
}

function addAssetLink() {
  assetLinks.value.push({ asset_type: "external", asset_id: "", label: "" })
}

async function save() {
  if (saving.value || !isValid.value)
    return
  saveError.value = false
  saving.value = true
  try {
    const entry = editing.value
      ? await updateResearchLogEntry(editing.value.id, {
        ...payload(),
        expected_revision: editing.value.revision,
        change_summary: changeSummary.value.trim(),
      })
      : await createResearchLogEntry(payload())
    window.$message?.success($t("page.recordDiary.logSaved"))
    visible.value = false
    emit("saved", entry)
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
.research-log-preview {
  border: 1px solid rgb(229 231 235);
  border-radius: 0.75rem;
  background: rgb(249 250 251);
  padding: 1.25rem;
}

.research-log-asset-row {
  display: grid;
  grid-template-columns: minmax(9rem, 0.8fr) minmax(10rem, 1fr) minmax(10rem, 1fr) auto;
  gap: 0.5rem;
}

@media (max-width: 640px) {
  .research-log-asset-row {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
