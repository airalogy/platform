<template>
  <n-button secondary @click="open">
    {{ $t("page.research.addHumanWork") }}
  </n-button>

  <n-modal
    v-model:show="visible"
    preset="card"
    class="human-work-modal"
    :title="$t('page.research.addHumanWork')"
    :mask-closable="false"
    @after-leave="reset"
  >
    <n-alert type="info" class="mb-4">
      {{ $t("page.research.humanWorkBoundary") }}
    </n-alert>

    <template v-if="!preview">
      <n-form label-placement="top">
        <n-form-item :label="$t('page.research.workTitle')" required>
          <n-input v-model:value="draft.title" :placeholder="$t('page.research.humanWorkTitlePlaceholder')" />
        </n-form-item>
        <n-form-item :label="$t('page.research.instructions')" required>
          <n-input
            v-model:value="draft.instructions"
            type="textarea"
            :autosize="{ minRows: 3, maxRows: 10 }"
            :placeholder="$t('page.research.humanWorkInstructionsPlaceholder')"
          />
        </n-form-item>
        <n-form-item :label="$t('page.research.completionCriteria')">
          <n-input
            v-model:value="draft.completionCriteria"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 6 }"
          />
        </n-form-item>
        <div class="grid grid-cols-1 gap-x-4 sm:grid-cols-2">
          <n-form-item :label="$t('page.research.evidenceKind')" required>
            <n-select v-model:value="draft.evidenceKind" :options="evidenceOptions" />
          </n-form-item>
          <n-form-item :label="$t('page.research.assignedTo')">
            <n-select
              v-model:value="draft.assigneeUserId"
              :options="executorOptions"
              filterable
              clearable
              :placeholder="$t('page.research.executorTaskOwner')"
            />
          </n-form-item>
        </div>

        <div class="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div>
            <div class="aira-type-label">{{ $t("page.research.submissionFields") }}</div>
            <div class="aira-type-meta mt-1">{{ $t("page.research.submissionFieldsHint") }}</div>
          </div>
          <n-button size="small" secondary :disabled="draft.fields.length >= 20" @click="addField">
            {{ $t("page.research.addField") }}
          </n-button>
        </div>
        <div class="space-y-3">
          <section v-for="(field, index) in draft.fields" :key="field.localId" class="human-field-card">
            <div class="mb-3 flex items-center justify-between gap-2">
              <strong class="aira-type-label">{{ $t("page.research.fieldNumber", { number: index + 1 }) }}</strong>
              <n-button quaternary size="small" :disabled="draft.fields.length === 1" @click="removeField(index)">
                {{ $t("common.delete") }}
              </n-button>
            </div>
            <div class="grid grid-cols-1 gap-x-3 sm:grid-cols-2">
              <n-form-item :label="$t('page.research.fieldLabel')" required>
                <n-input v-model:value="field.label" @blur="fillFieldKey(field)" />
              </n-form-item>
              <n-form-item
                :label="$t('page.research.fieldKey')"
                required
                :validation-status="fieldKeyError(field) ? 'error' : undefined"
                :feedback="fieldKeyError(field)"
              >
                <n-input v-model:value="field.key" placeholder="sample_condition" />
              </n-form-item>
              <n-form-item :label="$t('page.research.fieldType')" required>
                <n-select v-model:value="field.valueType" :options="fieldTypeOptions" />
              </n-form-item>
              <n-form-item :label="$t('page.research.requiredField')">
                <n-switch v-model:value="field.required" />
              </n-form-item>
            </div>
            <n-form-item :label="$t('page.research.fieldDescription')">
              <n-input v-model:value="field.description" />
            </n-form-item>
            <n-form-item
              v-if="field.valueType === 'choice'"
              :label="$t('page.research.choiceOptions')"
              required
              :validation-status="choiceOptionsError(field) ? 'error' : undefined"
              :feedback="choiceOptionsError(field)"
            >
              <n-input v-model:value="field.optionsText" :placeholder="$t('page.research.choiceOptionsPlaceholder')" />
            </n-form-item>
            <n-form-item v-if="field.valueType === 'number'" :label="$t('page.research.unit')">
              <n-input v-model:value="field.unit" placeholder="Cel" />
            </n-form-item>
          </section>
        </div>

        <div class="grid grid-cols-1 mt-4 gap-x-4 sm:grid-cols-2">
          <n-form-item :label="$t('page.research.minimumDataAssets')">
            <n-input-number v-model:value="draft.minimumAssets" :min="0" :max="20" />
          </n-form-item>
          <n-form-item
            :label="$t('page.research.maximumDataAssets')"
            :validation-status="draft.minimumAssets > draft.maximumAssets ? 'error' : undefined"
            :feedback="draft.minimumAssets > draft.maximumAssets ? $t('page.research.dataAssetRangeInvalid') : undefined"
          >
            <n-input-number v-model:value="draft.maximumAssets" :min="0" :max="20" />
          </n-form-item>
        </div>
      </n-form>
    </template>

    <template v-else>
      <n-alert type="warning">
        {{ $t("page.research.humanWorkPreviewHint") }}
      </n-alert>
      <section class="human-work-preview mt-4">
        <div class="aira-type-eyebrow">{{ $t("page.research.saveDestination") }}</div>
        <h3 class="aira-type-card-title mb-0 mt-1">{{ preview.destination.task.title }}</h3>
        <p class="aira-type-body aira-text-secondary mb-0 mt-2">
          {{ requestPayload.title }}
        </p>
        <div class="aira-type-meta mt-2">
          {{ $t("page.research.assignedTo") }} · {{ preview.assignee.name || preview.assignee.username }}
        </div>
        <ul class="human-work-effects">
          <li v-for="effect in preview.effects" :key="effect">{{ effect }}</li>
        </ul>
      </section>
    </template>

    <template #footer>
      <div class="flex flex-wrap justify-end gap-2">
        <n-button @click="preview ? preview = null : visible = false">
          {{ preview ? $t("page.research.backToEdit") : $t("common.cancel") }}
        </n-button>
        <n-button v-if="!preview" type="primary" :disabled="!canPreview" :loading="submitting" @click="previewAction">
          {{ $t("page.research.previewAction") }}
        </n-button>
        <n-button v-else type="primary" :loading="submitting" @click="confirmAction">
          {{ $t("page.research.confirmAction") }}
        </n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import type {
  HumanWorkRequest,
  HumanWorkValueType,
  ManualHumanWorkActionPreview,
  ResearchUser,
} from "@/service/api/research-tasks"
import { fetchEligibleResearchExecutors } from "@/service/api/research-executor-bindings"
import {
  createManualHumanWorkAction,
  previewManualHumanWorkAction,
} from "@/service/api/research-tasks"
import { useAuthStore } from "@/store/modules/auth"
import { $t } from "@airalogy/shared/locales"
import { nanoid } from "nanoid"

interface EditableField {
  localId: string
  key: string
  label: string
  description: string
  valueType: HumanWorkValueType
  required: boolean
  optionsText: string
  unit: string
}

const props = defineProps<{
  taskId: string
  projectId: string
  owner: ResearchUser
}>()
const emit = defineEmits<{ created: [] }>()
const authStore = useAuthStore()

const visible = ref(false)
const submitting = ref(false)
const preview = ref<ManualHumanWorkActionPreview | null>(null)
const eligibleExecutors = ref<ResearchUser[]>([])

function newField(): EditableField {
  return {
    localId: nanoid(8),
    key: "",
    label: "",
    description: "",
    valueType: "text",
    required: true,
    optionsText: "",
    unit: "",
  }
}

const draft = reactive({
  title: "",
  instructions: "",
  completionCriteria: "",
  evidenceKind: "observation" as HumanWorkRequest["evidence_kind"],
  assigneeUserId: "",
  minimumAssets: 0,
  maximumAssets: 0,
  fields: [newField()],
  idempotencyKey: "",
})

const evidenceOptions = computed(() => [
  "observation",
  "measurement",
  "analysis",
  "citation",
  "validation",
].map(value => ({
  value,
  label: $t(`page.research.evidenceKindValue.${value}` as I18n.I18nKey),
})))
const fieldTypeOptions = computed(() => [
  "text",
  "long_text",
  "number",
  "boolean",
  "date",
  "choice",
].map(value => ({
  value,
  label: $t(`page.research.humanFieldType.${value}` as I18n.I18nKey),
})))
const executorOptions = computed(() => {
  const people = new Map<string, ResearchUser>()
  people.set(props.owner.id, props.owner)
  for (const user of eligibleExecutors.value)
    people.set(user.id, user)
  return [...people.values()].map(user => ({
    value: user.id,
    label: user.name ? `${user.name} (@${user.username})` : `@${user.username}`,
  }))
})
const canPreview = computed(() => {
  const fieldKeys = draft.fields.map(field => field.key.trim())
  const fieldsAreValid = draft.fields.every((field) => {
    if (!field.label.trim() || !/^[a-z][a-z0-9_]{0,63}$/.test(field.key.trim()))
      return false
    if (field.valueType !== "choice")
      return true
    const options = parseChoiceOptions(field.optionsText)
    return options.length >= 2 && new Set(options).size === options.length
  })
  return Boolean(
    draft.title.trim()
    && draft.instructions.trim()
    && draft.minimumAssets <= draft.maximumAssets
    && draft.fields.length
    && fieldsAreValid
    && new Set(fieldKeys).size === fieldKeys.length,
  )
})
const requestPayload = computed<HumanWorkRequest>(() => ({
  title: draft.title.trim(),
  instructions: draft.instructions.trim(),
  completion_criteria: draft.completionCriteria.trim(),
  evidence_kind: draft.evidenceKind,
  fields: draft.fields.map(field => ({
    key: field.key.trim(),
    label: field.label.trim(),
    description: field.description.trim(),
    value_type: field.valueType,
    required: field.required,
    options: field.valueType === "choice" ? parseChoiceOptions(field.optionsText) : [],
    unit: field.valueType === "number" ? field.unit.trim() : "",
  })),
  data_asset_min_count: draft.minimumAssets,
  data_asset_max_count: draft.maximumAssets,
}))

function parseChoiceOptions(value: string) {
  return value.split(",").map(item => item.trim()).filter(Boolean)
}

function fieldKeyError(field: EditableField) {
  const key = field.key.trim()
  if (!key || !/^[a-z][a-z0-9_]{0,63}$/.test(key))
    return $t("page.research.fieldKeyInvalid")
  if (draft.fields.filter(item => item.key.trim() === key).length > 1)
    return $t("page.research.fieldKeyDuplicate")
  return undefined
}

function choiceOptionsError(field: EditableField) {
  const options = parseChoiceOptions(field.optionsText)
  return options.length < 2 || new Set(options).size !== options.length
    ? $t("page.research.choiceOptionsInvalid")
    : undefined
}

function addField() {
  if (draft.fields.length < 20)
    draft.fields.push(newField())
}

function removeField(index: number) {
  if (draft.fields.length > 1)
    draft.fields.splice(index, 1)
}

function fillFieldKey(field: EditableField) {
  if (field.key)
    return
  field.key = field.label
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 64)
}

async function open() {
  visible.value = true
  try {
    const result = await fetchEligibleResearchExecutors(props.projectId)
    eligibleExecutors.value = result.items
  }
  catch {
    eligibleExecutors.value = [props.owner]
  }
  const currentUserId = String(authStore.userInfo.id || "")
  draft.assigneeUserId = executorOptions.value.some(item => item.value === currentUserId)
    ? currentUserId
    : props.owner.id
}

function payload() {
  draft.idempotencyKey ||= `manual-human-${nanoid(16)}`
  return {
    assignee_user_id: draft.assigneeUserId || undefined,
    request: requestPayload.value,
    idempotency_key: draft.idempotencyKey,
  }
}

async function previewAction() {
  submitting.value = true
  try {
    preview.value = await previewManualHumanWorkAction(props.taskId, payload())
  }
  finally {
    submitting.value = false
  }
}

async function confirmAction() {
  if (!preview.value)
    return
  submitting.value = true
  try {
    await createManualHumanWorkAction(props.taskId, {
      ...payload(),
      preview_digest: preview.value.preview_digest,
    })
    window.$message?.success($t("page.research.humanWorkCreated"))
    visible.value = false
    emit("created")
  }
  finally {
    submitting.value = false
  }
}

function reset() {
  preview.value = null
  draft.title = ""
  draft.instructions = ""
  draft.completionCriteria = ""
  draft.evidenceKind = "observation"
  draft.assigneeUserId = ""
  draft.minimumAssets = 0
  draft.maximumAssets = 0
  draft.fields = [newField()]
  draft.idempotencyKey = ""
}
</script>

<style scoped>
.human-work-modal {
  width: min(50rem, calc(100vw - 2rem));
}

.human-field-card,
.human-work-preview {
  border: 1px solid rgb(229 231 235);
  border-radius: 0.85rem;
  padding: 1rem;
}

.human-work-effects {
  margin: 1rem 0 0;
  padding-left: 1.25rem;
  color: rgb(75 85 99);
}

.human-work-effects li + li {
  margin-top: 0.35rem;
}
</style>
