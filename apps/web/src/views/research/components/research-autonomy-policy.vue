<template>
  <n-button quaternary data-testid="research-policy-open" @click="open">
    <template #icon>
      <n-icon><icon-tabler-shield-check /></n-icon>
    </template>
    {{ $t("page.research.researchPolicy") }}
  </n-button>

  <n-modal
    v-model:show="visible"
    preset="card"
    :title="$t('page.research.researchPolicy')"
    class="research-policy-modal"
    :mask-closable="!submitting"
  >
    <n-spin :show="loading">
      <template v-if="snapshot">
        <n-alert type="info" :title="$t('page.research.assistedAlwaysAsks')">
          {{ $t("page.research.researchPolicyHint") }}
        </n-alert>

        <template v-if="!preview">
          <div class="mt-5 flex flex-wrap items-center justify-between gap-2">
            <div>
              <div class="aira-type-label">
                {{ snapshot.source === "lab_policy" ? $t("page.research.labPolicy") : $t("page.research.platformDefaultPolicy") }}
              </div>
              <div class="aira-type-meta mt-1">
                {{ $t("page.research.bindingRevision", { revision: snapshot.revision }) }}
                · {{ snapshot.policy_digest.slice(0, 12) }}
              </div>
            </div>
            <n-tag :type="canManage ? 'success' : 'default'" round>
              {{ canManage ? $t("page.research.policyManageAllowed") : $t("page.research.policyReadOnly") }}
            </n-tag>
          </div>

          <div class="grid mt-5 gap-4 lg:grid-cols-2">
            <section
              v-for="level in levels"
              :key="level.key"
              class="policy-level"
              :data-testid="`research-policy-${level.key}`"
            >
              <h3 class="aira-type-card-title mb-0">
                {{ level.label }}
              </h3>
              <p class="aira-type-meta mb-0 mt-1">
                {{ level.description }}
              </p>
              <div class="mt-4 space-y-4">
                <policy-switch
                  v-model="draft.policy[level.key].auto_approve_read_only_tools"
                  :disabled="!canManage"
                  :label="$t('page.research.autoReadOnlyTools')"
                  :hint="$t('page.research.autoReadOnlyToolsHint')"
                />
                <policy-switch
                  v-model="draft.policy[level.key].auto_create_wait_events"
                  :disabled="!canManage"
                  :label="$t('page.research.autoWaitEvents')"
                  :hint="$t('page.research.autoWaitEventsHint')"
                />
                <policy-switch
                  v-model="draft.policy[level.key].auto_approve_isolated_compute"
                  :disabled="!canManage"
                  :label="$t('page.research.autoIsolatedCompute')"
                  :hint="$t('page.research.autoIsolatedComputeHint')"
                />
              </div>
            </section>
          </div>

          <section class="policy-level mt-4">
            <h3 class="aira-type-card-title mb-0">
              {{ $t("page.research.automaticComputeLimits") }}
            </h3>
            <p class="aira-type-meta mb-0 mt-1">
              {{ $t("page.research.automaticComputeLimitsHint") }}
            </p>
            <div class="grid mt-4 gap-4 md:grid-cols-3">
              <label class="block">
                <span class="aira-type-label">{{ $t("page.research.maxAutomaticCost") }}</span>
                <n-input-number
                  v-model:value="maxEstimatedCost"
                  :disabled="!canManage || !automaticComputeEnabled"
                  :min="0"
                  :max="1000000"
                  class="mt-2 w-full"
                />
              </label>
              <label class="block">
                <span class="aira-type-label">{{ $t("page.research.currency") }}</span>
                <n-input
                  v-model:value="currency"
                  :disabled="!canManage || !automaticComputeEnabled"
                  maxlength="3"
                  class="mt-2"
                  placeholder="USD"
                />
              </label>
              <label class="block">
                <span class="aira-type-label">{{ $t("page.research.maxAutomaticRuntime") }}</span>
                <n-input-number
                  v-model:value="draft.policy.automatic_compute_limits.max_timeout_seconds"
                  :disabled="!canManage || !automaticComputeEnabled"
                  :min="1"
                  :max="86400"
                  class="mt-2 w-full"
                >
                  <template #suffix>s</template>
                </n-input-number>
              </label>
            </div>
            <n-alert v-if="automaticComputeEnabled" type="warning" class="mt-4">
              {{ $t("page.research.isolatedComputeBoundary") }}
            </n-alert>
          </section>

          <label v-if="canManage" class="mt-5 block">
            <span class="aira-type-label">{{ $t("page.research.changeReason") }}</span>
            <n-input
              v-model:value="draft.reason"
              data-testid="research-policy-reason"
              type="textarea"
              :autosize="{ minRows: 2, maxRows: 5 }"
              maxlength="4000"
              show-count
              class="mt-2"
              :placeholder="$t('page.research.researchPolicyReasonPlaceholder')"
            />
          </label>

          <n-collapse v-if="audits.length" class="mt-5">
            <n-collapse-item :title="$t('page.research.policyRevisionHistory')" name="history">
              <div class="space-y-3">
                <div v-for="audit in audits" :key="audit.id" class="policy-audit">
                  <div class="flex flex-wrap justify-between gap-2">
                    <span class="aira-type-label">{{ $t("page.research.bindingRevision", { revision: audit.revision }) }}</span>
                    <n-time class="aira-type-meta" :time="new Date(audit.created_at)" type="relative" />
                  </div>
                  <p class="aira-type-meta mb-0 mt-1 whitespace-pre-wrap">
                    {{ audit.reason }}
                  </p>
                </div>
              </div>
            </n-collapse-item>
          </n-collapse>
        </template>

        <template v-else>
          <n-alert type="warning" :title="$t('page.research.previewImpact')">
            {{ $t("page.research.researchPolicyFutureRunsOnly") }}
          </n-alert>
          <n-descriptions bordered :column="1" class="mt-4">
            <n-descriptions-item :label="$t('page.research.destination')">
              {{ preview.destination.lab_name }}
            </n-descriptions-item>
            <n-descriptions-item :label="$t('page.research.bindingRevision', { revision: preview.command.next_revision })">
              {{ String(preview.command.policy_digest).slice(0, 16) }}
            </n-descriptions-item>
          </n-descriptions>
          <ul class="aira-type-body aira-text-secondary mb-0 mt-4 pl-5">
            <li v-for="effect in preview.effects" :key="effect" class="mt-1">
              {{ effect }}
            </li>
          </ul>
        </template>
      </template>
    </n-spin>

    <template #footer>
      <div class="flex flex-wrap justify-end gap-2">
        <n-button :disabled="submitting" @click="handleBack">
          {{ preview ? $t("page.research.backToPolicy") : $t("common.close") }}
        </n-button>
        <n-button
          v-if="canManage && !preview"
          type="primary"
          :disabled="!canPreview"
          :loading="submitting"
          data-testid="research-policy-preview"
          @click="previewChange"
        >
          {{ $t("page.research.previewAction") }}
        </n-button>
        <n-button
          v-else-if="canManage && preview"
          type="primary"
          :loading="submitting"
          data-testid="research-policy-confirm"
          @click="confirmChange"
        >
          {{ $t("page.research.confirmPolicy") }}
        </n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import type {
  ResearchAutonomyPolicyAudit,
  ResearchAutonomyPolicyDraft,
  ResearchAutonomyPolicyPreview,
  ResearchAutonomyPolicySnapshot,
} from "@/service/api/research-autonomy-policies"
import {
  confirmResearchAutonomyPolicy,
  fetchResearchAutonomyPolicy,
  fetchResearchAutonomyPolicyAudits,
  previewResearchAutonomyPolicy,
} from "@/service/api/research-autonomy-policies"
import { $t } from "@airalogy/shared/locales"
import PolicySwitch from "./research-policy-switch.vue"

interface ProjectContext {
  lab_id?: string | number
}

const props = defineProps<{ project: ProjectContext }>()
const visible = ref(false)
const loading = ref(false)
const submitting = ref(false)
const canManage = ref(false)
const snapshot = ref<ResearchAutonomyPolicySnapshot | null>(null)
const audits = ref<ResearchAutonomyPolicyAudit[]>([])
const preview = ref<ResearchAutonomyPolicyPreview | null>(null)
const maxEstimatedCost = ref<number | null>(null)
const currency = ref("")
const draft = reactive<ResearchAutonomyPolicyDraft>({
  lab_id: "",
  expected_revision: 0,
  policy: {
    schema: "airalogy.research-autonomy-policy.v1",
    bounded_autopilot: {
      auto_approve_read_only_tools: true,
      auto_create_wait_events: false,
      auto_approve_isolated_compute: false,
    },
    autonomous_within_policy: {
      auto_approve_read_only_tools: true,
      auto_create_wait_events: false,
      auto_approve_isolated_compute: false,
    },
    automatic_compute_limits: { max_timeout_seconds: 3600 },
  },
  reason: "",
})

const levels = computed(() => [
  {
    key: "bounded_autopilot" as const,
    label: $t("page.research.autonomyBounded"),
    description: $t("page.research.autonomyBoundedPolicyHint"),
  },
  {
    key: "autonomous_within_policy" as const,
    label: $t("page.research.autonomyPolicy"),
    description: $t("page.research.autonomyFullPolicyHint"),
  },
])
const automaticComputeEnabled = computed(() =>
  draft.policy.bounded_autopilot.auto_approve_isolated_compute
  || draft.policy.autonomous_within_policy.auto_approve_isolated_compute,
)
const canPreview = computed(() => Boolean(
  draft.reason.trim()
  && (!automaticComputeEnabled.value
    || (maxEstimatedCost.value !== null && currency.value.trim().length === 3)),
))

function applySnapshot(value: ResearchAutonomyPolicySnapshot) {
  snapshot.value = value
  draft.lab_id = String(props.project.lab_id || "")
  draft.expected_revision = value.revision
  draft.policy = structuredClone(value.policy)
  draft.reason = ""
  maxEstimatedCost.value = value.policy.automatic_compute_limits.max_estimated_cost === undefined
    ? null
    : Number(value.policy.automatic_compute_limits.max_estimated_cost)
  currency.value = value.policy.automatic_compute_limits.currency || ""
}

async function load() {
  if (!props.project.lab_id)
    return
  loading.value = true
  try {
    const [result, history] = await Promise.all([
      fetchResearchAutonomyPolicy(String(props.project.lab_id)),
      fetchResearchAutonomyPolicyAudits(String(props.project.lab_id)),
    ])
    canManage.value = result.can_manage
    audits.value = history.items
    applySnapshot(result.policy)
  }
  finally {
    loading.value = false
  }
}

function open() {
  preview.value = null
  visible.value = true
  void load()
}

function payload(): ResearchAutonomyPolicyDraft {
  return {
    lab_id: draft.lab_id,
    expected_revision: draft.expected_revision,
    policy: {
      schema: draft.policy.schema,
      bounded_autopilot: { ...draft.policy.bounded_autopilot },
      autonomous_within_policy: { ...draft.policy.autonomous_within_policy },
      automatic_compute_limits: {
        max_timeout_seconds: draft.policy.automatic_compute_limits.max_timeout_seconds,
        ...(automaticComputeEnabled.value
          ? {
              max_estimated_cost: String(maxEstimatedCost.value),
              currency: currency.value.trim().toUpperCase(),
            }
          : {}),
      },
    },
    reason: draft.reason.trim(),
  }
}

async function previewChange() {
  submitting.value = true
  try {
    preview.value = await previewResearchAutonomyPolicy(payload())
  }
  finally {
    submitting.value = false
  }
}

async function confirmChange() {
  if (!preview.value)
    return
  submitting.value = true
  try {
    const result = await confirmResearchAutonomyPolicy({
      ...payload(),
      preview_digest: preview.value.preview_digest,
    })
    window.$message?.success($t("page.research.policySaved"))
    preview.value = null
    await load()
    applySnapshot(result.policy)
  }
  finally {
    submitting.value = false
  }
}

function handleBack() {
  if (preview.value) {
    preview.value = null
    return
  }
  visible.value = false
}
</script>

<style scoped>
.research-policy-modal {
  width: min(58rem, calc(100vw - 2rem));
}

.policy-level,
.policy-audit {
  border: 1px solid rgb(229 231 235);
  border-radius: 0.75rem;
  padding: 1rem;
}
</style>
