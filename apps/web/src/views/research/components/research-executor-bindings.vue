<template>
  <n-button secondary @click="open">
    <template #icon><n-icon><icon-tabler-settings /></n-icon></template>
    {{ $t("page.research.executorBindings") }}
  </n-button>

  <n-modal
    v-model:show="visible"
    preset="card"
    class="executor-binding-modal"
    :title="$t('page.research.executorBindings')"
    :mask-closable="false"
    @after-leave="resetEditor"
  >
    <n-alert type="info" class="mb-4">
      {{ $t("page.research.executorBindingsHint") }}
    </n-alert>

    <n-spin :show="loading">
      <template v-if="!editing">
        <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <div class="aira-type-eyebrow">{{ project.lab_name || project.lab_uid }}</div>
            <div class="aira-type-card-title mt-1">{{ project.name }}</div>
          </div>
          <div v-if="canManage" class="flex flex-wrap items-center gap-2">
            <research-human-executor-profiles
              :lab-id="String(project.lab_id || '')"
              @updated="loadHumanProfiles"
            />
            <n-button type="primary" @click="beginCreate">
              {{ $t("page.research.addExecutorBinding") }}
            </n-button>
          </div>
        </div>

        <div v-if="bindings.length" class="space-y-3">
          <article v-for="binding in bindings" :key="binding.id" class="executor-binding-card">
            <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div class="min-w-0">
                <div class="flex flex-wrap items-center gap-2">
                  <strong class="aira-type-label">{{ capabilityName(binding.capability_key) }}</strong>
                  <n-tag size="small" round>v{{ binding.capability_version }}</n-tag>
                  <n-tag :type="binding.enabled ? policyType(binding.approval_policy) : 'default'" size="small" round>
                    {{ binding.enabled ? policyLabel(binding.approval_policy) : $t("page.research.bindingDisabled") }}
                  </n-tag>
                </div>
                <p class="aira-type-meta mb-0 mt-2">
                  {{ executorLabel(binding) }} · {{ $t("page.research.bindingRevision", { revision: binding.revision }) }}
                </p>
                <p v-if="Object.keys(binding.constraints).length" class="aira-type-meta mb-0 mt-2 break-all">
                  {{ JSON.stringify(binding.constraints) }}
                </p>
              </div>
              <n-button v-if="canManage && canEditBinding(binding)" size="small" @click="beginEdit(binding)">
                {{ $t("common.edit") }}
              </n-button>
            </div>
          </article>
        </div>
        <n-empty v-else class="py-8" :description="$t('page.research.noExecutorBindings')" />
      </template>

      <template v-else-if="!preview">
        <n-form label-placement="top">
          <n-form-item v-if="!editingId" :label="$t('page.research.capability')" required>
            <n-select
              v-model:value="createDraft.capability_key"
              :options="capabilityOptions"
              filterable
              :placeholder="$t('page.research.selectCapability')"
              @update:value="applyCapability"
            />
          </n-form-item>
          <n-form-item
            v-if="!editingId && selectedCapability?.kind === 'protocol'"
            :label="$t('page.research.humanExecutor')"
            required
          >
            <n-select
              v-model:value="executorChoice"
              :options="executorOptions"
              filterable
              :placeholder="$t('page.research.selectHumanExecutor')"
              @update:value="applyExecutor"
            />
            <template #feedback>{{ $t("page.research.humanExecutorHint") }}</template>
          </n-form-item>
          <div
            v-if="skillPoolEditor"
            class="grid grid-cols-1 gap-x-4 sm:grid-cols-2"
          >
            <n-form-item :label="$t('page.research.requiredExecutorSkills')" required>
              <n-select
                v-model:value="requiredSkillKeys"
                :options="skillOptions"
                multiple
                filterable
                :placeholder="$t('page.research.selectRequiredExecutorSkills')"
              />
            </n-form-item>
            <n-form-item :label="$t('page.research.minimumSkillLevel')" required>
              <n-input-number v-model:value="minimumSkillLevel" :min="1" :max="5" />
            </n-form-item>
          </div>
          <n-alert v-if="skillPoolEditor && skillOptions.length === 0" type="warning" class="mb-4">
            {{ $t("page.research.noVerifiedExecutorSkills") }}
          </n-alert>
          <n-form-item :label="$t('page.research.approvalPolicy')" required>
            <n-select v-model:value="policy" :options="policyOptions" />
          </n-form-item>
          <div class="grid grid-cols-1 gap-x-4 sm:grid-cols-2">
            <n-form-item :label="$t('page.research.bindingPriority')">
              <n-input-number v-model:value="priority" :min="-1000" :max="1000" />
            </n-form-item>
            <n-form-item :label="$t('page.research.bindingEnabled')">
              <n-switch v-model:value="enabled" />
            </n-form-item>
          </div>
          <div class="grid grid-cols-1 gap-x-4 sm:grid-cols-2">
            <n-form-item :label="$t('page.research.maxActionsPerRun')">
              <n-input-number v-model:value="maxActionsPerRun" :min="1" :max="100" clearable />
            </n-form-item>
            <n-form-item :label="$t('page.research.onlyCurrentProject')">
              <n-switch v-model:value="onlyCurrentProject" />
            </n-form-item>
          </div>
          <n-form-item :label="$t('page.research.allowedAutonomyLevels')">
            <n-select v-model:value="allowedAutonomyLevels" :options="autonomyOptions" multiple clearable />
            <template #feedback>{{ $t("page.research.bindingConstraintsHint") }}</template>
          </n-form-item>
          <n-form-item :label="$t('page.research.changeReason')">
            <n-input v-model:value="reason" :placeholder="$t('page.research.changeReasonPlaceholder')" />
          </n-form-item>
        </n-form>
      </template>

      <template v-else>
        <section class="executor-binding-preview">
          <div class="aira-type-eyebrow">{{ $t("page.research.previewImpact") }}</div>
          <h3 class="aira-type-card-title mb-0 mt-2">
            {{ preview.capability?.name || capabilityName(String(preview.command.capability_key || "")) }}
          </h3>
          <dl class="executor-binding-facts mt-4">
            <div>
              <dt>{{ $t("page.research.approvalPolicy") }}</dt>
              <dd>{{ policyLabel(policy) }}</dd>
            </div>
            <div>
              <dt>{{ $t("page.research.bindingEnabled") }}</dt>
              <dd>{{ enabled ? $t("page.research.bindingEnabled") : $t("page.research.bindingDisabled") }}</dd>
            </div>
            <div v-if="selectedCapability?.kind === 'protocol' || editingProtocol">
              <dt>{{ $t("page.research.humanExecutor") }}</dt>
              <dd>{{ selectedExecutorLabel }}</dd>
            </div>
            <div v-if="skillPoolEditor">
              <dt>{{ $t("page.research.requiredExecutorSkills") }}</dt>
              <dd>{{ requiredSkillKeys.join(", ") }}</dd>
            </div>
          </dl>
          <p class="aira-type-meta mb-0 mt-4">
            {{ $t("page.research.bindingFutureRunsOnly") }}
          </p>
        </section>
      </template>
    </n-spin>

    <template #footer>
      <div class="flex flex-wrap justify-end gap-2">
        <n-button @click="handleBack">
          {{ editing ? $t("page.research.backToBindings") : $t("common.close") }}
        </n-button>
        <n-button
          v-if="editing && !preview"
          type="primary"
          :disabled="!canPreview"
          :loading="submitting"
          @click="previewChange"
        >
          {{ $t("page.research.previewAction") }}
        </n-button>
        <n-button v-else-if="editing && preview" type="primary" :loading="submitting" @click="confirmChange">
          {{ $t("page.research.confirmBinding") }}
        </n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import type { ResearchCapabilityDescriptor } from "@/service/api/research-capabilities"
import type {
  ExecutorApprovalPolicy,
  ExecutorBindingDraft,
  ExecutorBindingPreview,
  ResearchEligibleExecutor,
  ResearchExecutorBinding,
} from "@/service/api/research-executor-bindings"
import type { ResearchHumanExecutorProfile } from "@/service/api/research-human-executors"
import type { TagProps } from "naive-ui"
import { fetchResearchCapabilities } from "@/service/api/research-capabilities"
import {
  createExecutorBinding,
  fetchEligibleResearchExecutors,
  fetchExecutorBindings,
  previewExecutorBinding,
  previewExecutorBindingUpdate,
  updateExecutorBinding,
} from "@/service/api/research-executor-bindings"
import { fetchResearchHumanExecutorProfiles } from "@/service/api/research-human-executors"
import { $t } from "@airalogy/shared/locales"
import ResearchHumanExecutorProfiles from "./research-human-executor-profiles.vue"

interface ProjectContext {
  id: string | number
  name: string
  lab_id?: string | number
  lab_uid: string
  lab_name?: string
}

const props = defineProps<{ project: ProjectContext }>()

const visible = ref(false)
const loading = ref(false)
const submitting = ref(false)
const canManage = ref(false)
const editing = ref(false)
const editingId = ref("")
const bindings = ref<ResearchExecutorBinding[]>([])
const capabilities = ref<ResearchCapabilityDescriptor[]>([])
const eligibleExecutors = ref<ResearchEligibleExecutor[]>([])
const humanProfiles = ref<ResearchHumanExecutorProfile[]>([])
const preview = ref<ExecutorBindingPreview | null>(null)
const policy = ref<ExecutorApprovalPolicy>("always_ask")
const priority = ref(0)
const enabled = ref(true)
const maxActionsPerRun = ref<number | null>(null)
const onlyCurrentProject = ref(false)
const allowedAutonomyLevels = ref<string[]>([])
const reason = ref("")
const executorChoice = ref("task.owner")
const requiredSkillKeys = ref<string[]>([])
const minimumSkillLevel = ref(1)
const createDraft = reactive<ExecutorBindingDraft>({
  lab_id: "",
  capability_key: "",
  capability_version: "",
  executor_type: "platform_tool",
  executor_ref_type: "platform_worker",
  executor_ref_id: "",
  mode: "durable_job",
  approval_policy: "always_ask",
  constraints: {},
  priority: 0,
  enabled: true,
  reason: "",
})

const capabilityOptions = computed(() => capabilities.value
  .filter(item => item.kind !== "resource" && item.available)
  .map(item => ({
    label: `${item.kind === "protocol" ? "Protocol" : "Tool"} · ${item.name} · v${item.version}`,
    value: item.key,
  })))
const selectedCapability = computed(() =>
  capabilities.value.find(item => item.key === createDraft.capability_key),
)
const executorOptions = computed(() => [
  { label: $t("page.research.executorTaskOwner"), value: "task.owner" },
  { label: $t("page.research.executorSkillPool"), value: "skill_pool" },
  ...eligibleExecutors.value.map(user => ({
    label: user.name ? `${user.name} (@${user.username})` : `@${user.username}`,
    value: `user:${user.id}`,
  })),
])
const skillOptions = computed(() => {
  const items = new Map<string, string>()
  const now = Date.now()
  for (const profile of humanProfiles.value) {
    for (const skill of profile.skills) {
      if (skill.verified && (!skill.expires_at || new Date(skill.expires_at).getTime() > now))
        items.set(skill.key, `${skill.name} · ${skill.key}`)
    }
  }
  return [...items.entries()].map(([value, label]) => ({ label, value }))
})
const selectedExecutorLabel = computed(() => {
  return executorOptions.value.find(item => item.value === executorChoice.value)?.label
    || createDraft.executor_ref_id
})
const editingProtocol = computed(() => editingId.value
  ? bindings.value.find(item => item.id === editingId.value)?.capability_key.startsWith("protocol:")
  : false)
const skillPoolEditor = computed(() =>
  executorChoice.value === "skill_pool"
  && (selectedCapability.value?.kind === "protocol" || editingProtocol.value),
)
const policyOptions = computed(() => [
  { label: $t("page.research.policyAlwaysAsk"), value: "always_ask" },
  ...(selectedCapability.value?.kind === "protocol" || editingProtocol.value
    ? []
    : [{ label: $t("page.research.policyAllowReadOnly"), value: "allow_read_only" }]),
  { label: $t("page.research.policyDeny"), value: "deny" },
])
const canPreview = computed(() => {
  if (editingId.value)
    return !skillPoolEditor.value || requiredSkillKeys.value.length > 0
  return Boolean(
    createDraft.capability_key
    && (!skillPoolEditor.value || requiredSkillKeys.value.length),
  )
})
const autonomyOptions = computed(() => [
  { label: $t("page.research.autonomyAssisted"), value: "assisted" },
  { label: $t("page.research.autonomyBounded"), value: "bounded_autopilot" },
  { label: $t("page.research.autonomyPolicy"), value: "autonomous_within_policy" },
])

function policyLabel(value: ExecutorApprovalPolicy) {
  return {
    always_ask: $t("page.research.policyAlwaysAsk"),
    allow_read_only: $t("page.research.policyAllowReadOnly"),
    deny: $t("page.research.policyDeny"),
  }[value]
}

function policyType(value: ExecutorApprovalPolicy): TagProps["type"] {
  if (value === "deny")
    return "error"
  if (value === "allow_read_only")
    return "success"
  return "warning"
}

function capabilityName(key: string) {
  return capabilities.value.find(item => item.key === key)?.name || key
}

function executorLabel(binding: ResearchExecutorBinding) {
  if (binding.executor_ref.type === "task_role")
    return $t("page.research.executorTaskOwner")
  if (binding.executor_ref.type === "skill_pool") {
    const keys = Array.isArray(binding.constraints.required_skill_keys)
      ? binding.constraints.required_skill_keys.map(String)
      : []
    return $t("page.research.executorSkillPoolWithSkills", { skills: keys.join(", ") })
  }
  const user = eligibleExecutors.value.find(item => item.id === binding.executor_ref.id)
  return user
    ? (user.name ? `${user.name} (@${user.username})` : `@${user.username}`)
    : binding.executor_ref.id
}

function canEditBinding(binding: ResearchExecutorBinding) {
  const projectIds = binding.constraints.allowed_project_ids
  return !Array.isArray(projectIds)
    || projectIds.length === 0
    || (projectIds.length === 1 && projectIds[0] === String(props.project.id))
}

async function load() {
  if (!props.project.lab_id)
    return
  loading.value = true
  try {
    const [catalog, result, executors] = await Promise.all([
      fetchResearchCapabilities(String(props.project.id)),
      fetchExecutorBindings(String(props.project.lab_id)),
      fetchEligibleResearchExecutors(String(props.project.id)),
    ])
    capabilities.value = [...catalog.protocols, ...catalog.tools]
    bindings.value = result.items
    eligibleExecutors.value = executors.items
    canManage.value = result.can_manage
    if (result.can_manage)
      await loadHumanProfiles()
  }
  finally {
    loading.value = false
  }
}

function open() {
  visible.value = true
  void load()
}

async function loadHumanProfiles() {
  if (!props.project.lab_id || !canManage.value)
    return
  const result = await fetchResearchHumanExecutorProfiles(String(props.project.lab_id))
  humanProfiles.value = result.items
}

function beginCreate() {
  resetEditor()
  editing.value = true
  createDraft.lab_id = String(props.project.lab_id || "")
}

function beginEdit(binding: ResearchExecutorBinding) {
  resetEditor()
  editing.value = true
  editingId.value = binding.id
  policy.value = binding.approval_policy
  priority.value = binding.priority
  enabled.value = binding.enabled
  maxActionsPerRun.value = Number(binding.constraints.max_actions_per_run) || null
  allowedAutonomyLevels.value = Array.isArray(binding.constraints.allowed_autonomy_levels)
    ? binding.constraints.allowed_autonomy_levels.map(String)
    : []
  onlyCurrentProject.value = Boolean(
    Array.isArray(binding.constraints.allowed_project_ids)
    && binding.constraints.allowed_project_ids.includes(String(props.project.id)),
  )
  if (binding.executor_ref.type === "skill_pool") {
    executorChoice.value = "skill_pool"
    requiredSkillKeys.value = Array.isArray(binding.constraints.required_skill_keys)
      ? binding.constraints.required_skill_keys.map(String)
      : []
    minimumSkillLevel.value = Number(binding.constraints.minimum_skill_level) || 1
  }
}

function applyCapability(key: string) {
  const item = capabilities.value.find(capability => capability.key === key)
  if (!item)
    return
  createDraft.capability_version = item.version
  if (item.kind === "protocol") {
    createDraft.executor_type = "human"
    createDraft.executor_ref_type = "task_role"
    createDraft.executor_ref_id = "task.owner"
    executorChoice.value = "task.owner"
    createDraft.mode = "protocol_record"
    if (policy.value === "allow_read_only")
      policy.value = "always_ask"
  }
  else {
    createDraft.executor_type = "platform_tool"
    createDraft.executor_ref_type = "platform_worker"
    createDraft.executor_ref_id = item.source_id
    createDraft.mode = "durable_job"
  }
}

function applyExecutor(value: string) {
  if (value === "task.owner") {
    createDraft.executor_ref_type = "task_role"
    createDraft.executor_ref_id = value
    return
  }
  if (value === "skill_pool") {
    createDraft.executor_ref_type = "skill_pool"
    createDraft.executor_ref_id = "lab.skills"
    return
  }
  if (value.startsWith("user:")) {
    createDraft.executor_ref_type = "user"
    createDraft.executor_ref_id = value.slice("user:".length)
  }
}

function resetEditor() {
  editing.value = false
  editingId.value = ""
  preview.value = null
  policy.value = "always_ask"
  priority.value = 0
  enabled.value = true
  maxActionsPerRun.value = null
  onlyCurrentProject.value = false
  allowedAutonomyLevels.value = []
  reason.value = ""
  executorChoice.value = "task.owner"
  requiredSkillKeys.value = []
  minimumSkillLevel.value = 1
  createDraft.capability_key = ""
  createDraft.capability_version = ""
}

function handleBack() {
  if (preview.value) {
    preview.value = null
    return
  }
  if (editing.value) {
    resetEditor()
    return
  }
  visible.value = false
}

function createPayload(constraints: Record<string, unknown>): ExecutorBindingDraft {
  return {
    ...createDraft,
    approval_policy: policy.value,
    constraints,
    priority: priority.value,
    enabled: enabled.value,
    reason: reason.value.trim(),
  }
}

function bindingConstraints(): Record<string, unknown> {
  return {
    allowed_project_ids: onlyCurrentProject.value ? [String(props.project.id)] : [],
    allowed_autonomy_levels: allowedAutonomyLevels.value,
    ...(maxActionsPerRun.value ? { max_actions_per_run: maxActionsPerRun.value } : {}),
    ...(skillPoolEditor.value
      ? {
          required_skill_keys: requiredSkillKeys.value,
          minimum_skill_level: minimumSkillLevel.value,
        }
      : {}),
  }
}

function updatePayload(constraints: Record<string, unknown>) {
  const current = bindings.value.find(item => item.id === editingId.value)
  if (!current)
    throw new Error("Executor Binding not found")
  return {
    expected_revision: current.revision,
    approval_policy: policy.value,
    constraints,
    priority: priority.value,
    enabled: enabled.value,
    reason: reason.value.trim(),
  }
}

async function previewChange() {
  const constraints = bindingConstraints()
  submitting.value = true
  try {
    preview.value = editingId.value
      ? await previewExecutorBindingUpdate(editingId.value, updatePayload(constraints))
      : await previewExecutorBinding(createPayload(constraints))
  }
  finally {
    submitting.value = false
  }
}

async function confirmChange() {
  if (!preview.value)
    return
  const constraints = bindingConstraints()
  submitting.value = true
  try {
    if (editingId.value) {
      await updateExecutorBinding(editingId.value, {
        ...updatePayload(constraints),
        preview_digest: preview.value.preview_digest,
      })
    }
    else {
      await createExecutorBinding({
        ...createPayload(constraints),
        preview_digest: preview.value.preview_digest,
      })
    }
    window.$message?.success($t("page.research.bindingSaved"))
    resetEditor()
    await load()
  }
  finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.executor-binding-modal {
  width: min(52rem, calc(100vw - 2rem));
}

.executor-binding-card,
.executor-binding-preview {
  border: 1px solid rgb(229 231 235);
  border-radius: 0.85rem;
  padding: 1rem;
}

.executor-binding-facts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(10rem, 1fr));
  gap: 0.75rem;
  margin-bottom: 0;
}

.executor-binding-facts > div {
  border-radius: 0.7rem;
  background: rgb(248 250 252);
  padding: 0.75rem;
}

.executor-binding-facts dt {
  color: rgb(107 114 128);
  font-size: 0.75rem;
}

.executor-binding-facts dd {
  margin: 0.25rem 0 0;
  font-weight: 600;
}
</style>
