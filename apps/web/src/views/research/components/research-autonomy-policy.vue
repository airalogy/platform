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
                {{
                  snapshot.source === "lab_policy"
                    ? $t("page.research.labPolicy")
                    : $t("page.research.platformDefaultPolicy")
                }}
              </div>
              <div class="aira-type-meta mt-1">
                {{ $t("page.research.bindingRevision", { revision: snapshot.revision }) }}
                · {{ snapshot.policy_digest.slice(0, 12) }}
              </div>
            </div>
            <n-tag :type="canManage ? 'success' : 'default'" round>
              {{
                canManage
                  ? $t("page.research.policyManageAllowed")
                  : $t("page.research.policyReadOnly")
              }}
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

          <section
            v-if="canManage"
            class="policy-level mt-4"
            data-testid="research-autonomy-grants"
          >
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h3 class="aira-type-card-title mb-0">
                  {{ $t("page.research.evaluatedAutonomyGrants") }}
                </h3>
                <p class="aira-type-meta mb-0 mt-1">
                  {{ $t("page.research.evaluatedAutonomyGrantsHint") }}
                </p>
              </div>
              <n-tag type="warning" round>
                {{ $t("page.research.autonomyThreeGates") }}
              </n-tag>
            </div>

            <n-alert type="warning" class="mt-4">
              {{ $t("page.research.autonomyGrantBoundary") }}
            </n-alert>

            <div v-if="activeGrants.length" class="mt-4">
              <div class="aira-type-label mb-2">
                {{ $t("page.research.activeAutonomyGrants") }}
              </div>
              <div class="space-y-3">
                <article
                  v-for="grant in activeGrants"
                  :key="grant.id"
                  class="autonomy-grant-card"
                  :data-testid="`research-autonomy-grant-${grant.target.target_digest}`"
                >
                  <div class="flex flex-wrap items-start justify-between gap-3">
                    <div class="min-w-0">
                      <div class="aira-type-card-title break-all">
                        {{ grant.target.capability_key }}
                      </div>
                      <div class="aira-type-meta mt-1 break-all">
                        v{{ grant.target.capability_version }} · {{ grant.target.executor_type }} ·
                        {{ grant.target.executor_digest.slice(0, 12) }}
                      </div>
                    </div>
                    <div class="flex flex-wrap gap-2">
                      <n-tag :type="isGrantExpired(grant) ? 'error' : 'success'" round>
                        {{
                          isGrantExpired(grant)
                            ? $t("page.research.autonomyGrantExpired")
                            : $t("page.research.autonomyGrantActive")
                        }}
                      </n-tag>
                      <n-button
                        v-if="grant.enabled"
                        size="small"
                        tertiary
                        type="error"
                        :disabled="submitting"
                        :data-testid="`research-autonomy-revoke-${grant.target.target_digest}`"
                        @click="beginRevoke(grant)"
                      >
                        {{ $t("page.research.revokeAutonomyGrant") }}
                      </n-button>
                    </div>
                  </div>
                  <div class="aira-type-meta mt-3 flex flex-wrap gap-x-4 gap-y-1">
                    <span>{{ autonomyLevelNames(grant.allowed_levels) }}</span>
                    <span>{{ $t("page.research.autonomyGrantExpires") }}
                      <n-time :time="new Date(grant.valid_until)" /></span>
                    <span>{{
                      $t("page.research.supervisedSuccessCount", {
                        count: grant.evaluation.completed_count,
                      })
                    }}</span>
                    <span>r{{ grant.revision }}</span>
                  </div>
                </article>
              </div>
            </div>

            <div class="mt-5">
              <div class="aira-type-label mb-2">
                {{ $t("page.research.autonomyEvaluationCandidates") }}
              </div>
              <n-empty
                v-if="!evaluations.length"
                size="small"
                :description="$t('page.research.noAutonomyEvaluationHistory')"
              />
              <div v-else class="space-y-3">
                <article
                  v-for="evaluation in evaluations"
                  :key="evaluation.target.target_digest"
                  class="autonomy-grant-card"
                  :data-testid="`research-autonomy-evaluation-${evaluation.target.target_digest}`"
                >
                  <div class="flex flex-wrap items-start justify-between gap-3">
                    <div class="min-w-0">
                      <div class="aira-type-card-title break-all">
                        {{ evaluation.target.capability_key }}
                      </div>
                      <div class="aira-type-meta mt-1 break-all">
                        v{{ evaluation.target.capability_version }} ·
                        {{ evaluation.target.executor_type }}
                      </div>
                    </div>
                    <n-button
                      size="small"
                      :type="evaluation.passed ? 'primary' : 'default'"
                      :disabled="!evaluation.passed || submitting"
                      :data-testid="`research-autonomy-grant-open-${evaluation.target.target_digest}`"
                      @click="beginGrant(evaluation)"
                    >
                      {{
                        grantFor(evaluation.target.target_digest)
                          ? $t("page.research.renewAutonomyGrant")
                          : $t("page.research.createAutonomyGrant")
                      }}
                    </n-button>
                  </div>
                  <div class="mt-3 flex flex-wrap items-center gap-2">
                    <n-tag :type="evaluation.passed ? 'success' : 'warning'" round>
                      {{
                        evaluation.passed
                          ? $t("page.research.autonomyEvaluationPassed")
                          : $t("page.research.autonomyEvaluationPending")
                      }}
                    </n-tag>
                    <span class="aira-type-meta">
                      {{
                        $t("page.research.autonomyEvaluationProgress", {
                          completed: evaluation.completed_count,
                          required: evaluation.criteria.minimum_supervised_successes,
                        })
                      }}
                    </span>
                    <span v-if="evaluation.failure_count" class="aira-type-meta text-red-600">
                      {{
                        $t("page.research.autonomyEvaluationFailures", {
                          count: evaluation.failure_count,
                        })
                      }}
                    </span>
                  </div>
                </article>
              </div>
            </div>
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
                    <span class="aira-type-label">{{
                      $t("page.research.bindingRevision", { revision: audit.revision })
                    }}</span>
                    <n-time
                      class="aira-type-meta"
                      :time="new Date(audit.created_at)"
                      type="relative"
                    />
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
            <n-descriptions-item
              :label="
                $t('page.research.bindingRevision', { revision: preview.command.next_revision })
              "
            >
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

  <n-modal
    v-model:show="grantVisible"
    preset="card"
    :title="
      grantMode === 'revoke'
        ? $t('page.research.revokeAutonomyGrant')
        : $t('page.research.configureAutonomyGrant')
    "
    class="research-grant-modal"
    :mask-closable="!submitting"
  >
    <template v-if="selectedTarget">
      <n-alert :type="grantMode === 'revoke' ? 'error' : 'warning'">
        {{
          grantMode === "revoke"
            ? $t("page.research.revokeAutonomyGrantHint")
            : $t("page.research.configureAutonomyGrantHint")
        }}
      </n-alert>

      <n-descriptions bordered :column="1" class="mt-4">
        <n-descriptions-item :label="$t('page.research.capability')">
          {{ selectedTarget.capability_key }} · v{{ selectedTarget.capability_version }}
        </n-descriptions-item>
        <n-descriptions-item :label="$t('page.research.executor')">
          {{ selectedTarget.executor_type }} · {{ selectedTarget.executor_digest.slice(0, 16) }}
        </n-descriptions-item>
        <n-descriptions-item
          v-if="selectedEvaluation"
          :label="$t('page.research.autonomyEvaluation')"
        >
          {{
            $t("page.research.supervisedSuccessCount", {
              count: selectedEvaluation.completed_count,
            })
          }}
          · {{ selectedEvaluation.evaluation_digest.slice(0, 16) }}
        </n-descriptions-item>
      </n-descriptions>

      <template v-if="!grantPreview">
        <template v-if="grantMode === 'grant'">
          <div class="mt-5">
            <div class="aira-type-label mb-2">
              {{ $t("page.research.allowedAutonomyLevels") }}
            </div>
            <n-checkbox-group
              v-model:value="grantLevels"
              data-testid="research-autonomy-grant-levels"
            >
              <div class="flex flex-wrap gap-4">
                <n-checkbox
                  value="bounded_autopilot"
                  :label="$t('page.research.autonomyBounded')"
                />
                <n-checkbox
                  value="autonomous_within_policy"
                  :label="$t('page.research.autonomyPolicy')"
                />
              </div>
            </n-checkbox-group>
          </div>
          <label class="mt-5 block">
            <span class="aira-type-label">{{ $t("page.research.autonomyGrantExpires") }}</span>
            <n-date-picker
              v-model:value="grantExpiry"
              type="datetime"
              class="mt-2 w-full"
              :is-date-disabled="isGrantDateDisabled"
              data-testid="research-autonomy-grant-expiry"
            />
          </label>
        </template>
        <label class="mt-5 block">
          <span class="aira-type-label">{{ $t("page.research.changeReason") }}</span>
          <n-input
            v-model:value="grantReason"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 5 }"
            maxlength="4000"
            show-count
            class="mt-2"
            data-testid="research-autonomy-grant-reason"
            :placeholder="$t('page.research.autonomyGrantReasonPlaceholder')"
          />
        </label>
      </template>

      <template v-else>
        <n-alert type="warning" class="mt-4" :title="$t('page.research.previewImpact')">
          {{ $t("page.research.autonomyGrantFutureRunsOnly") }}
        </n-alert>
        <ul class="aira-type-body aira-text-secondary mb-0 mt-4 pl-5">
          <li v-for="effect in grantPreview.effects" :key="effect" class="mt-1">
            {{ effect }}
          </li>
        </ul>
      </template>
    </template>

    <template #footer>
      <div class="flex flex-wrap justify-end gap-2">
        <n-button :disabled="submitting" @click="closeOrBackGrant">
          {{ grantPreview ? $t("page.research.backToPolicy") : $t("common.cancel") }}
        </n-button>
        <n-button
          v-if="!grantPreview"
          :type="grantMode === 'revoke' ? 'error' : 'primary'"
          :disabled="!canPreviewGrant"
          :loading="submitting"
          data-testid="research-autonomy-grant-preview"
          @click="previewGrantChange"
        >
          {{ $t("page.research.previewAction") }}
        </n-button>
        <n-button
          v-else
          :type="grantMode === 'revoke' ? 'error' : 'primary'"
          :loading="submitting"
          data-testid="research-autonomy-grant-confirm"
          @click="confirmGrantChange"
        >
          {{
            grantMode === "revoke"
              ? $t("page.research.confirmRevokeAutonomyGrant")
              : $t("page.research.confirmAutonomyGrant")
          }}
        </n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import type {
  ResearchAutonomyEvaluation,
  ResearchAutonomyGrant,
  ResearchAutonomyGrantPreview,
  ResearchAutonomyGrantRevokePreview,
  ResearchAutonomyLevel,
  ResearchAutonomyPolicyAudit,
  ResearchAutonomyPolicyDraft,
  ResearchAutonomyPolicyPreview,
  ResearchAutonomyPolicySnapshot,
  ResearchAutonomyTarget,
} from "@/service/api/research-autonomy-policies"
import {
  confirmResearchAutonomyGrant,
  confirmResearchAutonomyGrantRevocation,
  confirmResearchAutonomyPolicy,
  fetchResearchAutonomyEvaluations,
  fetchResearchAutonomyGrants,
  fetchResearchAutonomyPolicy,
  fetchResearchAutonomyPolicyAudits,
  previewResearchAutonomyGrant,
  previewResearchAutonomyGrantRevocation,
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
const evaluations = ref<ResearchAutonomyEvaluation[]>([])
const grants = ref<ResearchAutonomyGrant[]>([])
const preview = ref<ResearchAutonomyPolicyPreview | null>(null)
const grantVisible = ref(false)
const grantMode = ref<"grant" | "revoke">("grant")
const selectedEvaluation = ref<ResearchAutonomyEvaluation | null>(null)
const selectedGrant = ref<ResearchAutonomyGrant | null>(null)
const grantPreview = ref<ResearchAutonomyGrantPreview | ResearchAutonomyGrantRevokePreview | null>(
  null,
)
const grantLevels = ref<ResearchAutonomyLevel[]>(["bounded_autopilot"])
const grantExpiry = ref<number | null>(null)
const grantReason = ref("")
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
const automaticComputeEnabled = computed(
  () =>
    draft.policy.bounded_autopilot.auto_approve_isolated_compute
    || draft.policy.autonomous_within_policy.auto_approve_isolated_compute,
)
const canPreview = computed(() =>
  Boolean(
    draft.reason.trim()
    && (!automaticComputeEnabled.value
      || (maxEstimatedCost.value !== null && currency.value.trim().length === 3)),
  ),
)
const activeGrants = computed(() => grants.value.filter(item => item.enabled))
const selectedTarget = computed<ResearchAutonomyTarget | null>(
  () => selectedEvaluation.value?.target || selectedGrant.value?.target || null,
)
const canPreviewGrant = computed(() =>
  Boolean(
    grantReason.value.trim()
    && (grantMode.value === "revoke"
      || (grantLevels.value.length && grantExpiry.value && grantExpiry.value > Date.now())),
  ),
)

function applySnapshot(value: ResearchAutonomyPolicySnapshot) {
  snapshot.value = value
  draft.lab_id = String(props.project.lab_id || "")
  draft.expected_revision = value.revision
  draft.policy = structuredClone(value.policy)
  draft.reason = ""
  maxEstimatedCost.value
    = value.policy.automatic_compute_limits.max_estimated_cost === undefined
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
    if (result.can_manage) {
      await loadGrantData()
    }
    else {
      evaluations.value = []
      grants.value = []
    }
  }
  finally {
    loading.value = false
  }
}

async function loadGrantData() {
  if (!props.project.lab_id || !canManage.value)
    return
  const [evaluationResult, grantResult] = await Promise.all([
    fetchResearchAutonomyEvaluations(String(props.project.lab_id)),
    fetchResearchAutonomyGrants(String(props.project.lab_id)),
  ])
  evaluations.value = evaluationResult.items
  grants.value = grantResult.items
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

function grantFor(targetDigest: string) {
  return grants.value.find(item => item.target.target_digest === targetDigest)
}

function isGrantExpired(grant: ResearchAutonomyGrant) {
  return new Date(grant.valid_until).getTime() <= Date.now()
}

function autonomyLevelNames(values: ResearchAutonomyLevel[]) {
  return values
    .map(value =>
      value === "bounded_autopilot"
        ? $t("page.research.autonomyBounded")
        : $t("page.research.autonomyPolicy"),
    )
    .join(" · ")
}

function isGrantDateDisabled(timestamp: number) {
  const now = Date.now()
  return timestamp < now - 86_400_000 || timestamp > now + 365 * 86_400_000
}

function resetGrantDialog() {
  grantPreview.value = null
  grantReason.value = ""
  grantExpiry.value = Date.now() + 90 * 86_400_000
  grantLevels.value = ["bounded_autopilot"]
}

function beginGrant(evaluation: ResearchAutonomyEvaluation) {
  const current = grantFor(evaluation.target.target_digest) || null
  grantMode.value = "grant"
  selectedEvaluation.value = evaluation
  selectedGrant.value = current
  resetGrantDialog()
  if (current) {
    grantLevels.value = [...current.allowed_levels]
    grantReason.value = current.reason
    const currentExpiry = new Date(current.valid_until).getTime()
    grantExpiry.value = currentExpiry > Date.now() ? currentExpiry : Date.now() + 90 * 86_400_000
  }
  grantVisible.value = true
}

function beginRevoke(grant: ResearchAutonomyGrant) {
  grantMode.value = "revoke"
  selectedGrant.value = grant
  selectedEvaluation.value = grant.evaluation
  resetGrantDialog()
  grantVisible.value = true
}

function grantDraft() {
  if (!selectedTarget.value || !grantExpiry.value)
    throw new Error("Autonomy grant target is unavailable")
  return {
    lab_id: String(props.project.lab_id || ""),
    target_digest: selectedTarget.value.target_digest,
    expected_revision: selectedGrant.value?.revision || 0,
    allowed_levels: grantLevels.value,
    valid_until: new Date(grantExpiry.value).toISOString(),
    reason: grantReason.value.trim(),
  }
}

function grantRevokeDraft() {
  if (!selectedGrant.value)
    throw new Error("Autonomy grant is unavailable")
  return {
    lab_id: String(props.project.lab_id || ""),
    expected_revision: selectedGrant.value.revision,
    reason: grantReason.value.trim(),
  }
}

async function previewGrantChange() {
  submitting.value = true
  try {
    if (grantMode.value === "revoke") {
      if (!selectedGrant.value)
        return
      grantPreview.value = await previewResearchAutonomyGrantRevocation(
        selectedGrant.value.id,
        grantRevokeDraft(),
      )
    }
    else {
      grantPreview.value = await previewResearchAutonomyGrant(grantDraft())
    }
  }
  finally {
    submitting.value = false
  }
}

async function confirmGrantChange() {
  if (!grantPreview.value)
    return
  submitting.value = true
  try {
    if (grantMode.value === "revoke") {
      if (!selectedGrant.value)
        return
      await confirmResearchAutonomyGrantRevocation(selectedGrant.value.id, {
        ...grantRevokeDraft(),
        preview_digest: grantPreview.value.preview_digest,
      })
      window.$message?.success($t("page.research.autonomyGrantRevoked"))
    }
    else {
      await confirmResearchAutonomyGrant({
        ...grantDraft(),
        preview_digest: grantPreview.value.preview_digest,
      })
      window.$message?.success($t("page.research.autonomyGrantSaved"))
    }
    await loadGrantData()
    grantVisible.value = false
  }
  finally {
    submitting.value = false
  }
}

function closeOrBackGrant() {
  if (grantPreview.value) {
    grantPreview.value = null
    return
  }
  grantVisible.value = false
}
</script>

<style scoped>
.research-policy-modal {
  width: min(68rem, calc(100vw - 2rem));
}

.research-grant-modal {
  width: min(42rem, calc(100vw - 2rem));
}

.policy-level,
.policy-audit,
.autonomy-grant-card {
  border: 1px solid rgb(229 231 235);
  border-radius: 0.75rem;
  padding: 1rem;
}
</style>
