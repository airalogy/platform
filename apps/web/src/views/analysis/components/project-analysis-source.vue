<template>
  <div class="project-source" data-testid="project-source">
    <n-form-item :label="t('page.analysis.protocol')" required>
      <n-select
        :value="model.protocol_id || null"
        :options="options"
        filterable
        data-testid="project-source-protocol"
        @update:value="selectProtocol"
      />
    </n-form-item>
    <template v-if="model.protocol_id">
      <div class="source-scope mb-4">
        <p class="aira-type-label mb-2">
          {{ t("page.analysis.sourceScope") }}
        </p>
        <p class="aira-type-body" data-testid="project-source-selection">
          {{
            model.selection.mode === "selected"
              ? t("page.analysis.selectedScope", { count: model.selection.records.length })
              : t("page.analysis.filteredScope")
          }}
        </p>
        <p v-for="(value, key) in model.selection.filters" :key="key" class="aira-type-meta">
          {{ key }}: {{ value }}
        </p>
        <details v-if="model.selection.mode === 'selected'" class="aira-type-meta mb-3">
          <summary>{{ t("page.analysis.provenance") }}</summary>
          <p v-for="record in model.selection.records" :key="record.id">
            Record {{ record.id }} · v{{ record.version }}
          </p>
        </details>
        <div class="flex flex-wrap gap-2">
          <n-button size="small" data-testid="project-source-select-records" @click="openPicker">
            {{ t("page.projectAnalysis.chooseRecords") }}
          </n-button>
          <n-button size="small" data-testid="project-source-use-latest" @click="useLatest">
            {{ t("page.analysis.useLatest") }}
          </n-button>
        </div>
      </div>
      <n-alert v-if="error" type="error" class="mb-3">
        {{ error }}
      </n-alert>
      <n-alert v-if="ownOnly" type="info" class="mb-3">
        {{ t("page.analysis.ownRecordsOnly") }}
      </n-alert>
      <n-spin :show="loading">
        <slot />
      </n-spin>
    </template>
    <n-modal
      v-model:show="pickerVisible"
      preset="card"
      class="aira-dialog"
      style="--aira-dialog-width: 42rem"
      :title="t('page.projectAnalysis.chooseRecords')"
      data-testid="project-record-picker"
    >
      <p class="aira-type-meta">
        {{ t("page.projectAnalysis.exactRecordsHint") }}
      </p>
      <n-input
        v-model:value="search"
        :placeholder="t('common.search')"
        clearable
        @keyup.enter="loadRecords(1)"
      >
        <template #suffix>
          <n-button text @click="loadRecords(1)">
            {{ t("common.search") }}
          </n-button>
        </template>
      </n-input>
      <n-alert v-if="pickerError" type="error" class="my-3">
        {{ pickerError }}
      </n-alert>
      <n-spin :show="pickerLoading">
        <div class="py-3 space-y-3">
          <n-checkbox
            v-for="record in records"
            :key="record.record_id"
            :checked="picked.some(item => item.id === record.record_id)"
            class="record-choice"
            @update:checked="checked => toggleRecord(record, checked)"
          >
            #{{ record.metadata.record_num }} · v{{ record.record_version }} · Protocol
            {{ record.metadata.protocol_version }}<br>
            <span class="aira-type-meta">{{ record.record_id }}</span>
          </n-checkbox>
        </div>
        <div class="flex items-center justify-between gap-2">
          <n-button :disabled="page <= 1" @click="loadRecords(page - 1)">
            {{ t("common.previous") }}
          </n-button>
          <span>{{ page }} / {{ Math.max(1, Math.ceil(total / 20)) }}</span>
          <n-button :disabled="page * 20 >= total" @click="loadRecords(page + 1)">
            {{ t("common.next") }}
          </n-button>
        </div>
      </n-spin>
      <template #footer>
        <div class="flex flex-wrap justify-end gap-2">
          <n-button @click="pickerVisible = false">
            {{ t("common.cancel") }}
          </n-button>
          <n-button
            type="primary"
            :disabled="!picked.length || pickerLoading"
            data-testid="project-confirm-records"
            @click="applyRecords"
          >
            {{ t("page.projectAnalysis.useSelected", { count: picked.length }) }}
          </n-button>
        </div>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import type { AnalysisField, AnalysisRecordReference } from "@/service/api/analysis"
import type {
  ProjectAnalysisProtocol,
  ProjectAnalysisSelection,
} from "@/service/api/project-analysis"
import type { ProtocolModels } from "@airalogy/shared/types"
import { fetchProjectAnalysisSourceContext } from "@/service/api/project-analysis"
import { fetchProtocolRecords } from "@/service/api/project-protocols"
import { copyProjectRecordReferences } from "@/utils/project-analysis"
import { useI18n } from "vue-i18n"

const props = defineProps<{ projectId: string, protocols: ProjectAnalysisProtocol[], usedProtocolIds: string[] }>()
const emit = defineEmits<{
  fields: [fields: AnalysisField[]]
  changedProtocol: []
  validity: [valid: boolean]
}>()
const model = defineModel<ProjectAnalysisSelection["inputs"][number]>({ required: true })
const { t } = useI18n()
const loading = ref(false)
const error = ref("")
const ownOnly = ref(false)
let sequence = 0
const options = computed(() =>
  props.protocols.map(protocol => ({
    value: protocol.protocol_id,
    label: protocol.protocol_name,
    disabled:
      protocol.protocol_id !== model.value.protocol_id
      && props.usedProtocolIds.includes(protocol.protocol_id),
  })),
)
const pickerVisible = ref(false)
const pickerLoading = ref(false)
const pickerError = ref("")
const records = ref<ProtocolModels.RecordInfo[]>([])
const picked = ref<AnalysisRecordReference[]>([])
const page = ref(1)
const total = ref(0)
const search = ref("")
function selectProtocol(protocolId: string) {
  model.value = {
    ...model.value,
    protocol_id: protocolId,
    selection: { mode: "latest", filters: {} },
  }
  emit("changedProtocol")
}
function useLatest() {
  model.value = { ...model.value, selection: { mode: "latest", filters: {} } }
}
function errorText(cause: unknown) {
  const detail = (cause as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return typeof detail === "string" ? detail : t("page.analysis.requestError")
}
async function loadContext() {
  const current = ++sequence
  emit("fields", [])
  emit("validity", false)
  error.value = ""
  if (!model.value.protocol_id)
    return
  loading.value = true
  try {
    const context = await fetchProjectAnalysisSourceContext(props.projectId, model.value.protocol_id, model.value.selection)
    if (current !== sequence)
      return
    ownOnly.value = context.own_records_only
    emit("fields", context.fields)
    emit("validity", true)
  }
  catch (cause) {
    if (current === sequence)
      error.value = errorText(cause)
  }
  finally {
    if (current === sequence)
      loading.value = false
  }
}
async function openPicker() {
  picked.value
    = model.value.selection.mode === "selected"
      ? copyProjectRecordReferences(model.value.selection.records)
      : []
  pickerVisible.value = true
  await loadRecords(1)
}
async function loadRecords(target: number) {
  pickerLoading.value = true
  pickerError.value = ""
  try {
    const response = await fetchProtocolRecords(model.value.protocol_id, {
      page: target,
      pageSize: 20,
      q: search.value || undefined,
    })
    if (response.error || !response.data)
      throw response.error
    records.value = response.data.records
    total.value = response.data.total_count
    page.value = target
  }
  catch (cause) {
    pickerError.value = errorText(cause)
  }
  finally {
    pickerLoading.value = false
  }
}
function toggleRecord(record: ProtocolModels.RecordInfo, checked: boolean) {
  picked.value = picked.value.filter(item => item.id !== record.record_id)
  if (checked)
    picked.value.push({ id: record.record_id, version: record.record_version })
}
function applyRecords() {
  model.value = {
    ...model.value,
    selection: { mode: "selected", filters: {}, records: copyProjectRecordReferences(picked.value) },
  }
  pickerVisible.value = false
}
watch(
  () => model.value,
  () => void loadContext(),
  { immediate: true, deep: true },
)
onBeforeUnmount(() => {
  sequence += 1
})
</script>

<style scoped>
.project-source {
  min-width: 0;
}
.source-scope {
  padding: 12px;
  border-radius: 8px;
  background: #f7f9fc;
  overflow-wrap: anywhere;
}
.record-choice {
  display: flex;
  overflow-wrap: anywhere;
}
</style>
