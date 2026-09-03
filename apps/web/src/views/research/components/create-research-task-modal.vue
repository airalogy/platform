<template>
  <n-button type="primary" @click="openModal">
    <template #icon>
      <n-icon><icon-tabler-sparkles /></n-icon>
    </template>
    {{ $t("page.research.createTask") }}
  </n-button>

  <n-modal
    v-model:show="visible"
    preset="card"
    class="research-task-modal"
    :title="$t('page.research.createTitle')"
    :mask-closable="false"
    @after-leave="resetPreview"
  >
    <n-alert v-if="!instanceStore.aiEnabled" type="info" class="mb-5">
      {{ $t("page.research.aiOffHint") }}
    </n-alert>

    <template v-if="!preview">
      <n-form label-placement="top" :show-require-mark="true">
        <div class="grid grid-cols-1 gap-x-4 md:grid-cols-2">
          <n-form-item :label="$t('page.research.project')" required>
            <n-select
              v-model:value="form.project_id"
              :options="projectOptions"
              :loading="projectsLoading"
              :disabled="Boolean(props.project)"
              filterable
              @update:value="handleProjectChange"
            />
          </n-form-item>
          <n-form-item :label="$t('page.research.autonomy')" required>
            <n-select v-model:value="form.autonomy_level" :options="autonomyOptions" />
          </n-form-item>
        </div>

        <n-form-item :label="$t('page.research.taskName')" required>
          <n-input v-model:value="form.title" :placeholder="$t('page.research.taskNamePlaceholder')" />
        </n-form-item>
        <n-form-item :label="$t('page.research.goal')" required>
          <n-input
            v-model:value="form.goal"
            type="textarea"
            :autosize="{ minRows: 3, maxRows: 8 }"
            :placeholder="$t('page.research.goalPlaceholder')"
          />
        </n-form-item>
        <n-form-item :label="$t('page.research.successCriteria')" required>
          <n-input
            v-model:value="criteriaText"
            type="textarea"
            :autosize="{ minRows: 3, maxRows: 7 }"
            :placeholder="$t('page.research.criteriaPlaceholder')"
          />
        </n-form-item>
        <n-form-item :label="$t('page.research.stopConditions')">
          <n-input
            v-model:value="stopText"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 6 }"
            :placeholder="$t('page.research.stopPlaceholder')"
          />
        </n-form-item>
        <div class="grid grid-cols-1 gap-x-4 md:grid-cols-2">
          <n-form-item
            :label="$t('page.research.deadline')"
            :validation-status="deadlineInvalid ? 'error' : undefined"
            :feedback="deadlineInvalid ? $t('page.research.deadlineFuture') : undefined"
          >
            <n-date-picker
              v-model:value="deadlineAt"
              type="datetime"
              clearable
              class="w-full"
              :placeholder="$t('page.research.deadlinePlaceholder')"
              :is-date-disabled="isDeadlineDisabled"
            />
          </n-form-item>
          <n-form-item :label="$t('page.research.budgetLimit')">
            <n-input-group>
              <n-input
                v-model:value="form.budget_limit"
                inputmode="decimal"
                :placeholder="$t('page.research.budgetLimitPlaceholder')"
              />
              <n-select
                v-model:value="form.budget_currency"
                class="w-28"
                :options="currencyOptions"
                filterable
                tag
              />
            </n-input-group>
          </n-form-item>
        </div>
        <n-form-item :label="$t('page.research.methods')">
          <n-select
            v-model:value="form.protocol_ids"
            :options="protocolOptions"
            :loading="protocolsLoading"
            :disabled="!form.project_id"
            multiple
            filterable
            clearable
            :placeholder="$t('page.research.methodsPlaceholder')"
          />
          <template #feedback>
            {{ $t("page.research.methodsHint") }}
          </template>
        </n-form-item>
        <n-form-item :label="$t('page.research.digitalCapabilities')">
          <n-select
            v-model:value="form.tool_keys"
            :options="toolOptions"
            :loading="capabilitiesLoading"
            :disabled="!form.project_id"
            multiple
            clearable
            :placeholder="$t('page.research.digitalCapabilitiesPlaceholder')"
          />
          <template #feedback>
            {{ $t("page.research.digitalCapabilitiesHint") }}
          </template>
        </n-form-item>
        <n-form-item :label="$t('page.research.resourceRequirements')">
          <n-select
            v-model:value="form.resource_type_ids"
            :options="resourceOptions"
            :loading="capabilitiesLoading"
            :disabled="!form.project_id"
            multiple
            filterable
            clearable
            :placeholder="$t('page.research.resourceRequirementsPlaceholder')"
          />
          <template #feedback>
            {{ $t("page.research.resourceRequirementsHint") }}
          </template>
        </n-form-item>
        <n-form-item :label="$t('page.research.externalServices')">
          <n-select
            v-model:value="form.service_offering_ids"
            :options="serviceOptions"
            :loading="capabilitiesLoading"
            :disabled="!form.project_id"
            multiple
            filterable
            clearable
            :placeholder="$t('page.research.externalServicesPlaceholder')"
          />
          <template #feedback>
            {{ $t("page.research.externalServicesHint") }}
          </template>
        </n-form-item>
        <n-form-item :label="$t('page.research.knowledgeContext')">
          <n-select
            v-model:value="form.knowledge_ids"
            :options="knowledgeOptions"
            :loading="knowledgeLoading"
            :disabled="!form.project_id"
            multiple
            filterable
            clearable
            :placeholder="$t('page.research.knowledgePlaceholder')"
          />
          <template #feedback>
            {{ $t("page.research.knowledgeHint") }}
          </template>
        </n-form-item>
      </n-form>
    </template>

    <template v-else>
      <div class="space-y-5">
        <n-alert :type="preview.ai_path_available ? 'success' : 'info'">
          {{
            preview.ai_path_available
              ? $t("page.research.previewAiPath")
              : $t("page.research.previewManualPath")
          }}
        </n-alert>
        <section class="research-preview-card">
          <div class="aira-type-eyebrow">
            {{ $t("page.research.saveDestination") }}
          </div>
          <div class="aira-type-card-title mt-2">
            {{ preview.destination.lab.name }} / {{ preview.destination.project.name }}
          </div>
          <p class="aira-type-body aira-text-secondary mb-0 mt-2">
            {{ form.title }}
          </p>
        </section>
        <section class="research-preview-card">
          <div class="aira-type-eyebrow">
            {{ $t("page.research.operationalLimits") }}
          </div>
          <div class="aira-type-body aira-text-secondary mt-2 space-y-1">
            <div>
              {{ $t("page.research.deadline") }} ·
              {{ preview.operational_limits.deadline_at ? new Date(preview.operational_limits.deadline_at).toLocaleString() : $t("page.research.noLimit") }}
            </div>
            <div>
              {{ $t("page.research.budgetLimit") }} ·
              <template v-if="preview.operational_limits.budget_limit">
                {{ preview.operational_limits.budget_limit }} {{ preview.operational_limits.budget_currency }}
              </template>
              <template v-else>
                {{ $t("page.research.noLimit") }}
              </template>
            </div>
          </div>
        </section>
        <section class="research-preview-card">
          <div class="aira-type-eyebrow">
            {{ $t("page.research.pinnedDigitalCapabilities") }}
          </div>
          <div v-if="preview.tools.length" class="mt-3 flex flex-wrap gap-2">
            <n-tag v-for="tool in preview.tools" :key="tool.key" round type="info">
              {{ tool.name }} · v{{ tool.version }}
            </n-tag>
          </div>
          <p v-else class="aira-type-body aira-text-muted mb-0 mt-2">
            {{ $t("page.research.noDigitalCapabilities") }}
          </p>
        </section>
        <section class="research-preview-card">
          <div class="aira-type-eyebrow">
            {{ $t("page.research.resolvedExecutors") }}
          </div>
          <div v-if="preview.executor_bindings.length" class="mt-3 space-y-2">
            <div v-for="binding in preview.executor_bindings" :key="binding.capability_key" class="flex flex-wrap items-center justify-between gap-2">
              <span class="aira-type-label break-all">{{ binding.capability_key }}</span>
              <div class="flex flex-wrap gap-2">
                <n-tag size="small" round>
                  {{ executorBindingLabel(binding.executor_type) }}
                </n-tag>
                <n-tag size="small" round :type="binding.approval_policy === 'allow_read_only' ? 'success' : 'warning'">
                  {{ executorPolicyLabel(binding.approval_policy) }}
                </n-tag>
              </div>
            </div>
          </div>
        </section>
        <section class="research-preview-card">
          <div class="aira-type-eyebrow">
            {{ $t("page.research.pinnedKnowledge") }}
          </div>
          <div v-if="preview.knowledge.length" class="mt-3 flex flex-wrap gap-2">
            <n-tag v-for="item in preview.knowledge" :key="item.id" round type="success">
              {{ item.title }} · r{{ item.revision }}
            </n-tag>
          </div>
          <p v-else class="aira-type-body aira-text-muted mb-0 mt-2">
            {{ $t("page.research.noKnowledge") }}
          </p>
        </section>
        <section class="research-preview-card">
          <div class="aira-type-eyebrow">
            {{ $t("page.research.resourceRequirements") }}
          </div>
          <div v-if="preview.resources.length" class="mt-3 flex flex-wrap gap-2">
            <n-tag v-for="item in preview.resources" :key="item.key" round type="warning">
              {{ item.name }} · r{{ item.version }}
            </n-tag>
          </div>
          <p v-else class="aira-type-body aira-text-muted mb-0 mt-2">
            {{ $t("page.research.noResourceRequirements") }}
          </p>
        </section>
        <section class="research-preview-card">
          <div class="aira-type-eyebrow">
            {{ $t("page.research.externalServices") }}
          </div>
          <div v-if="preview.services.length" class="mt-3 flex flex-wrap gap-2">
            <n-tag v-for="item in preview.services" :key="item.source_revision_id" round type="info">
              {{ item.metadata.provider.name }} · {{ item.name }} · v{{ item.version }}
            </n-tag>
          </div>
          <p v-else class="aira-type-body aira-text-muted mb-0 mt-2">
            {{ $t("page.research.noExternalServices") }}
          </p>
        </section>
        <section class="research-preview-card">
          <div class="aira-type-eyebrow">
            {{ $t("page.research.confirmedMethods") }}
          </div>
          <div v-if="preview.protocols.length" class="mt-3 flex flex-wrap gap-2">
            <n-tag v-for="protocol in preview.protocols" :key="protocol.id" round>
              {{ protocol.name }} · v{{ protocol.version }}
            </n-tag>
          </div>
          <p v-else class="aira-type-body aira-text-muted mb-0 mt-2">
            {{ $t("page.research.noMethods") }}
          </p>
        </section>
        <section class="research-preview-card">
          <div class="aira-type-eyebrow">
            {{ $t("page.research.effects") }}
          </div>
          <ul class="aira-type-body aira-text-secondary mb-0 mt-2 pl-5">
            <li v-for="effect in localizedEffects" :key="effect">
              {{ effect }}
            </li>
          </ul>
        </section>
        <n-alert v-for="warning in localizedWarnings" :key="warning" type="warning">
          {{ warning }}
        </n-alert>
      </div>
    </template>

    <template #footer>
      <div class="flex flex-wrap items-center justify-end gap-2">
        <n-button @click="preview ? resetPreview() : closeModal()">
          {{ preview ? $t("page.research.backToEdit") : $t("common.cancel") }}
        </n-button>
        <n-button
          v-if="!preview"
          type="primary"
          :disabled="!isValid"
          :loading="submitting"
          @click="handlePreview"
        >
          {{ $t("page.research.previewTask") }}
        </n-button>
        <n-button v-else type="primary" :loading="submitting" @click="handleCreate">
          {{ $t("page.research.confirmCreate") }}
        </n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import type {
  KnowledgeItem,
} from "@/service/api/knowledge"
import type { ResearchCapabilityDescriptor } from "@/service/api/research-capabilities"
import type {
  ResearchEnvironmentExecutorBinding,
  ResearchTaskDetail,
  ResearchTaskDraft,
  ResearchTaskPreview,
} from "@/service/api/research-tasks"
import type { ProtocolModels } from "@airalogy/shared/types"
import { fetchKnowledgeItems } from "@/service/api/knowledge"
import { fetchProtocols } from "@/service/api/project-protocols"
import { fetchResearchCapabilities } from "@/service/api/research-capabilities"
import { createResearchTask, previewResearchTask } from "@/service/api/research-tasks"
import { fetchUserProjects } from "@/service/api/users"
import { useAuthStore } from "@/store/modules/auth"
import { useInstanceStore } from "@/store/modules/instance"
import { $t } from "@airalogy/shared/locales"

interface ProjectContext {
  id: string | number
  uid: string
  name: string
  lab_uid: string
  lab_id?: string | number
  lab_name?: string
}

const props = defineProps<{ project?: ProjectContext | null }>()
const emit = defineEmits<{ created: [task: ResearchTaskDetail] }>()

const authStore = useAuthStore()
const instanceStore = useInstanceStore()
const visible = ref(false)
const projectsLoading = ref(false)
const protocolsLoading = ref(false)
const knowledgeLoading = ref(false)
const capabilitiesLoading = ref(false)
const submitting = ref(false)
const projects = ref<Api.Project.MyProjectInfo[]>([])
const protocols = ref<ProtocolModels.ProjectProtocolInfo[]>([])
const knowledgeItems = ref<KnowledgeItem[]>([])
const toolCapabilities = ref<ResearchCapabilityDescriptor[]>([])
const resourceCapabilities = ref<ResearchCapabilityDescriptor[]>([])
const serviceCapabilities = ref<ResearchCapabilityDescriptor[]>([])
const preview = ref<ResearchTaskPreview | null>(null)
const criteriaText = ref("")
const stopText = ref("")
const deadlineAt = ref<number | null>(null)
const RESEARCH_CREATOR_PROJECT_ROLES = new Set([1, 20, 30, 35])

function emptyForm(): ResearchTaskDraft {
  return {
    project_id: props.project ? String(props.project.id) : "",
    title: "",
    goal: "",
    success_criteria: [],
    stop_conditions: [],
    autonomy_level: "assisted",
    protocol_ids: [],
    tool_keys: [],
    knowledge_ids: [],
    resource_type_ids: [],
    service_offering_ids: [],
    budget_limit: "",
    budget_currency: "USD",
  }
}
const form = reactive<ResearchTaskDraft>(emptyForm())

const projectOptions = computed(() => {
  if (props.project) {
    return [{
      label: `${props.project.lab_name || props.project.lab_uid} / ${props.project.name}`,
      value: String(props.project.id),
    }]
  }
  return projects.value.map(project => ({
    label: `${project.lab_name || project.lab_uid} / ${project.name}`,
    value: String(project.id),
  }))
})
const protocolOptions = computed(() => protocols.value.map(protocol => ({
  label: `${protocol.name} · v${protocol.latest_version}`,
  value: String(protocol.id),
})))
const knowledgeOptions = computed(() => knowledgeItems.value.map(item => ({
  label: `${item.scope_type === "lab" ? $t("page.knowledge.scopeLab") : $t("page.knowledge.scopeProject")} · ${item.title} · r${item.revision}`,
  value: item.id,
})))
const toolOptions = computed(() => toolCapabilities.value.map(item => ({
  label: `${item.name} · v${item.version}`,
  value: String(item.metadata.tool_key || item.source_id),
  disabled: !item.available,
})))
const resourceOptions = computed(() => resourceCapabilities.value.map(item => ({
  label: `${item.name} · r${item.version}`,
  value: item.source_id,
  disabled: !item.available,
})))
const serviceOptions = computed(() => serviceCapabilities.value.map(item => ({
  label: `${String(item.metadata.provider?.name || "")} · ${item.name} · v${item.version}`,
  value: item.source_id,
  disabled: !item.available,
})))
const autonomyOptions = computed(() => [
  { label: $t("page.research.autonomyAssisted"), value: "assisted" },
  { label: $t("page.research.autonomyBounded"), value: "bounded_autopilot" },
  { label: $t("page.research.autonomyPolicy"), value: "autonomous_within_policy" },
])
const currencyOptions = ["USD", "CNY", "EUR", "GBP", "JPY"].map(value => ({
  label: value,
  value,
}))
const deadlineInvalid = computed(() => Boolean(deadlineAt.value && deadlineAt.value <= Date.now()))
const isValid = computed(() => Boolean(
  form.project_id
  && form.title.trim()
  && form.goal.trim()
  && lines(criteriaText.value).length
  && !deadlineInvalid.value
  && (!form.budget_limit || Number(form.budget_limit) > 0),
))
const localizedEffects = computed(() => preview.value
  ? [
      $t("page.research.effectCreate"),
      $t("page.research.effectPin"),
      preview.value.ai_path_available
        ? $t("page.research.effectAi")
        : $t("page.research.effectManual"),
    ]
  : [])
const localizedWarnings = computed(() => {
  if (!preview.value?.warnings.length)
    return []
  return [
    preview.value.ai_instance_available
      ? $t("page.research.warningNoCapability")
      : $t("page.research.warningManual"),
  ]
})

function executorBindingLabel(value: ResearchEnvironmentExecutorBinding["executor_type"]) {
  return value === "human"
    ? $t("page.research.executorTaskOwner")
    : $t("page.research.platformWorker")
}

function executorPolicyLabel(value: ResearchEnvironmentExecutorBinding["approval_policy"]) {
  return {
    always_ask: $t("page.research.policyAlwaysAsk"),
    allow_read_only: $t("page.research.policyAllowReadOnly"),
    deny: $t("page.research.policyDeny"),
  }[value]
}

function lines(value: string) {
  return value.split("\n").map(item => item.trim()).filter(Boolean)
}

function isDeadlineDisabled(timestamp: number) {
  return timestamp < new Date().setHours(0, 0, 0, 0)
}

function payload(): ResearchTaskDraft {
  return {
    ...form,
    title: form.title.trim(),
    goal: form.goal.trim(),
    success_criteria: lines(criteriaText.value),
    stop_conditions: lines(stopText.value),
    deadline_at: deadlineAt.value ? new Date(deadlineAt.value).toISOString() : undefined,
    budget_limit: form.budget_limit?.trim() || undefined,
    budget_currency: form.budget_limit?.trim() ? form.budget_currency : undefined,
  }
}

async function loadProjects() {
  if (props.project || !authStore.userInfo.id)
    return
  projectsLoading.value = true
  try {
    const result = await fetchUserProjects(authStore.userInfo.id, {
      page: 1,
      pageSize: 100,
      sortedBy: "updated_at",
    })
    projects.value = (result?.projects || []).filter(project =>
      Number(project.user_lab_role) <= 2
      || RESEARCH_CREATOR_PROJECT_ROLES.has(Number(project.user_role)),
    )
    if (projects.value.length === 1) {
      form.project_id = String(projects.value[0].id)
      await Promise.all([
        loadProtocols(form.project_id),
        loadCapabilities(form.project_id),
        loadKnowledge(form.project_id),
      ])
    }
  }
  finally {
    projectsLoading.value = false
  }
}

async function loadCapabilities(projectId: string) {
  toolCapabilities.value = []
  resourceCapabilities.value = []
  serviceCapabilities.value = []
  form.tool_keys = []
  form.resource_type_ids = []
  form.service_offering_ids = []
  if (!projectId)
    return
  capabilitiesLoading.value = true
  try {
    const catalog = await fetchResearchCapabilities(projectId)
    toolCapabilities.value = catalog.tools
    resourceCapabilities.value = catalog.resources
    serviceCapabilities.value = catalog.services
    const internalSearch = catalog.tools.find(item =>
      item.available && item.source_id === "knowledge.search",
    )
    if (internalSearch)
      form.tool_keys = [internalSearch.source_id]
  }
  finally {
    capabilitiesLoading.value = false
  }
}

async function loadProtocols(projectId: string) {
  protocols.value = []
  form.protocol_ids = []
  if (!projectId)
    return
  protocolsLoading.value = true
  try {
    const result = await fetchProtocols({ page: 1, pageSize: 100, projectId })
    if (result.error)
      throw result.error
    protocols.value = result.data?.protocols || []
  }
  finally {
    protocolsLoading.value = false
  }
}

async function loadKnowledge(projectId: string) {
  knowledgeItems.value = []
  form.knowledge_ids = []
  if (!projectId)
    return
  const project = props.project && String(props.project.id) === projectId
    ? props.project
    : projects.value.find(item => String(item.id) === projectId)
  if (!project?.lab_id)
    return
  knowledgeLoading.value = true
  try {
    const [projectKnowledge, labKnowledge] = await Promise.all([
      fetchKnowledgeItems({
        scope_type: "project",
        project_id: projectId,
        state: "reviewed",
        page: 1,
        pageSize: 100,
      }),
      fetchKnowledgeItems({
        scope_type: "lab",
        lab_id: String(project.lab_id),
        state: "reviewed",
        page: 1,
        pageSize: 100,
      }),
    ])
    knowledgeItems.value = [...projectKnowledge.items, ...labKnowledge.items]
      .filter(item => item.visibility !== "restricted")
  }
  finally {
    knowledgeLoading.value = false
  }
}

async function handleProjectChange(value: string) {
  resetPreview()
  await Promise.all([loadProtocols(value), loadCapabilities(value), loadKnowledge(value)])
}

async function openModal() {
  visible.value = true
  if (props.project) {
    form.project_id = String(props.project.id)
    if (!protocols.value.length && !knowledgeItems.value.length) {
      await Promise.all([
        loadProtocols(form.project_id),
        loadCapabilities(form.project_id),
        loadKnowledge(form.project_id),
      ])
    }
  }
  else if (!projects.value.length) {
    await loadProjects()
  }
}

function closeModal() {
  visible.value = false
}

function resetPreview() {
  preview.value = null
}

async function handlePreview() {
  if (!isValid.value)
    return
  submitting.value = true
  try {
    preview.value = await previewResearchTask(payload())
  }
  finally {
    submitting.value = false
  }
}

async function handleCreate() {
  if (!preview.value)
    return
  submitting.value = true
  try {
    const task = await createResearchTask({
      ...payload(),
      preview_digest: preview.value.preview_digest,
    })
    window.$message?.success($t("page.research.created"))
    visible.value = false
    emit("created", task)
  }
  finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.research-task-modal {
  width: min(48rem, calc(100vw - 2rem));
}

.research-preview-card {
  border: 1px solid rgb(229 231 235);
  border-radius: 0.75rem;
  background: rgb(249 250 251);
  padding: 1rem;
}
</style>
