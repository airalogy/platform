<template>
  <n-button secondary @click="open">
    {{ $t("page.research.addDigitalAction") }}
  </n-button>

  <n-modal
    v-model:show="visible"
    preset="card"
    class="research-digital-modal"
    :title="$t('page.research.addDigitalAction')"
    :mask-closable="false"
    @after-leave="reset"
  >
    <template v-if="!preview">
      <n-tabs v-model:value="mode" type="segment" animated>
        <n-tab-pane name="tool" :tab="$t('page.research.toolAction')">
          <n-alert type="info" class="mb-4">
            {{ $t("page.research.toolActionHint") }}
          </n-alert>
          <n-form label-placement="top">
            <n-form-item :label="$t('page.research.researchTool')" required>
              <n-select
                v-model:value="toolDraft.tool_key"
                :options="toolOptions"
                :loading="toolsLoading"
                :placeholder="$t('page.research.selectTool')"
              />
              <template #feedback>
                {{ selectedTool?.description || $t("page.research.noToolsAvailable") }}
              </template>
            </n-form-item>
            <template v-if="toolArgumentKind === 'search'">
              <n-form-item :label="$t('page.research.searchQuery')" required>
                <n-input
                  v-model:value="toolQuery"
                  :placeholder="$t('page.research.searchQueryPlaceholder')"
                />
              </n-form-item>
              <n-form-item :label="$t('page.research.resultLimit')">
                <n-input-number v-model:value="toolLimit" :min="1" :max="50" />
              </n-form-item>
            </template>
            <n-form-item v-else-if="toolArgumentKind === 'doi'" :label="$t('page.research.doi')" required>
              <n-input
                v-model:value="toolDoi"
                :placeholder="$t('page.research.doiPlaceholder')"
              />
            </n-form-item>
            <template v-else-if="toolArgumentKind === 'specialist'">
              <n-alert type="warning" class="mb-4">
                {{ $t("page.research.specialistBoundaryHint") }}
              </n-alert>
              <n-form-item :label="$t('page.research.specialistRole')" required>
                <n-select v-model:value="specialistRole" :options="specialistRoleOptions" />
              </n-form-item>
              <n-form-item :label="$t('page.research.specialistQuestion')" required>
                <n-input
                  v-model:value="specialistQuestion"
                  type="textarea"
                  :autosize="{ minRows: 3, maxRows: 8 }"
                  :placeholder="$t('page.research.specialistQuestionPlaceholder')"
                />
              </n-form-item>
              <n-form-item :label="$t('page.research.specialistDeliverable')">
                <n-input
                  v-model:value="specialistDeliverable"
                  type="textarea"
                  :autosize="{ minRows: 2, maxRows: 5 }"
                  :placeholder="$t('page.research.specialistDeliverablePlaceholder')"
                />
              </n-form-item>
            </template>
            <n-form-item
              v-else
              :label="$t('page.research.toolArguments')"
              required
              :validation-status="genericToolArguments ? undefined : 'error'"
              :feedback="genericToolArguments ? $t('page.research.toolSchemaHint') : $t('page.research.invalidJsonObject')"
            >
              <n-input
                v-model:value="toolArgumentsText"
                type="textarea"
                :autosize="{ minRows: 5, maxRows: 12 }"
                class="font-mono"
              />
            </n-form-item>
            <n-form-item :label="$t('page.research.actionTitle')">
              <n-input v-model:value="toolDraft.title" />
            </n-form-item>
            <n-form-item :label="$t('page.research.actionDescription')">
              <n-input
                v-model:value="toolDraft.description"
                type="textarea"
                :autosize="{ minRows: 2, maxRows: 6 }"
              />
            </n-form-item>
          </n-form>
        </n-tab-pane>

        <n-tab-pane name="instrument" :tab="$t('page.research.instrumentAction')">
          <n-alert type="warning" class="mb-4">
            {{ $t("page.research.instrumentActionHint") }}
          </n-alert>
          <n-form label-placement="top">
            <n-form-item :label="$t('page.research.instrumentCommand')" required>
              <n-select
                v-model:value="instrumentDraft.command_id"
                :options="instrumentOptions"
                :loading="instrumentsLoading"
                :placeholder="$t('page.research.selectInstrumentCommand')"
              />
              <template #feedback>
                {{ selectedInstrument?.description || $t("page.research.noInstrumentCommands") }}
              </template>
            </n-form-item>
            <n-form-item :label="$t('page.research.approvedBooking')" required>
              <n-select
                v-model:value="instrumentDraft.equipment_booking_id"
                :options="bookingOptions"
                :disabled="!selectedInstrument"
                :placeholder="$t('page.research.selectApprovedBooking')"
              />
              <template #feedback>
                {{ $t("page.research.instrumentBookingHint") }}
              </template>
            </n-form-item>
            <n-form-item
              :label="$t('page.research.instrumentArguments')"
              required
              :validation-status="instrumentArgumentsValid ? undefined : 'error'"
              :feedback="instrumentArgumentsValid ? $t('page.research.instrumentSchemaHint') : $t('page.research.invalidJsonObject')"
            >
              <n-input
                v-model:value="instrumentArgumentsText"
                type="textarea"
                :autosize="{ minRows: 4, maxRows: 12 }"
                class="font-mono"
              />
            </n-form-item>
            <n-form-item :label="$t('page.research.actionTitle')">
              <n-input v-model:value="instrumentDraft.title" />
            </n-form-item>
            <n-form-item :label="$t('page.research.actionDescription')">
              <n-input
                v-model:value="instrumentDraft.description"
                type="textarea"
                :autosize="{ minRows: 2, maxRows: 6 }"
              />
            </n-form-item>
          </n-form>
        </n-tab-pane>

        <n-tab-pane name="control" :tab="$t('page.research.instrumentControl')">
          <n-alert type="warning" class="mb-4">
            {{ $t("page.research.instrumentControlHint") }}
          </n-alert>
          <n-form label-placement="top">
            <div class="control-grid">
              <n-form-item :label="$t('page.research.controlMode')" required>
                <n-radio-group v-model:value="controlMode">
                  <n-space>
                    <n-radio value="bounded_sequence">
                      {{ $t("page.research.boundedSequence") }}
                    </n-radio>
                    <n-radio value="feedback_loop">
                      {{ $t("page.research.feedbackLoop") }}
                    </n-radio>
                  </n-space>
                </n-radio-group>
              </n-form-item>
              <n-form-item :label="$t('page.research.approvedBooking')" required>
                <n-select
                  v-model:value="controlBookingId"
                  :options="controlBookingOptions"
                  :loading="instrumentsLoading"
                  :placeholder="$t('page.research.selectApprovedBooking')"
                />
              </n-form-item>
            </div>
            <div class="control-grid">
              <n-form-item
                v-if="controlMode === 'feedback_loop'"
                :label="$t('page.research.maximumControlSteps')"
                required
              >
                <n-input-number v-model:value="controlMaxSteps" :min="controlSteps.length" :max="50" />
              </n-form-item>
              <n-form-item :label="$t('page.research.maximumDurationMinutes')" required>
                <n-input-number v-model:value="controlDurationMinutes" :min="1" :max="1440" />
              </n-form-item>
            </div>
            <section v-if="aiAvailable" class="aira-control-draft mb-4">
              <div class="aira-type-eyebrow">
                {{ $t("page.research.airaIntentEntry") }}
              </div>
              <h3 class="aira-type-card-title mb-0 mt-1">
                {{ $t("page.research.airaInstrumentControlDraft") }}
              </h3>
              <p class="aira-type-body aira-text-secondary mb-3 mt-2">
                {{ $t("page.research.airaInstrumentControlDraftHint") }}
              </p>
              <n-form-item :label="$t('page.research.controlGoal')" required>
                <n-input
                  v-model:value="airaControlInstruction"
                  type="textarea"
                  :autosize="{ minRows: 3, maxRows: 8 }"
                  :placeholder="$t('page.research.controlGoalPlaceholder')"
                />
              </n-form-item>
              <div class="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
                <n-form-item
                  :label="$t('page.research.maximumStepTemplates')"
                  class="mb-0"
                >
                  <n-input-number
                    v-model:value="airaStepTemplateLimit"
                    :min="1"
                    :max="controlMode === 'feedback_loop' ? Math.min(20, controlMaxSteps) : 20"
                  />
                </n-form-item>
                <n-button
                  type="primary"
                  secondary
                  :disabled="!airaControlInstruction.trim() || !controlBookingId"
                  :loading="airaControlDrafting"
                  @click="handleAiraControlDraft"
                >
                  {{ $t("page.research.generateControlDraft") }}
                </n-button>
              </div>
              <n-alert v-if="airaControlDraftResult" type="info" class="mt-4">
                <strong>{{ $t("page.research.airaRationale") }}</strong>
                <div class="mt-1">
                  {{ airaControlDraftResult.rationale }}
                </div>
                <ul
                  v-if="airaControlDraftResult.assumptions.length || airaControlDraftResult.warnings.length"
                  class="mb-0 mt-2 pl-5"
                >
                  <li v-for="item in airaControlDraftResult.assumptions" :key="`assumption-${item}`">
                    {{ item }}
                  </li>
                  <li v-for="item in airaControlDraftResult.warnings" :key="`warning-${item}`">
                    {{ item }}
                  </li>
                </ul>
                <div class="aira-type-meta mt-2">
                  {{ airaControlDraftResult.boundary }}
                </div>
              </n-alert>
            </section>
            <n-form-item :label="$t('page.research.actionTitle')" required>
              <n-input
                v-model:value="controlTitle"
                :placeholder="$t('page.research.instrumentControlTitlePlaceholder')"
              />
            </n-form-item>
            <n-form-item :label="$t('page.research.actionDescription')">
              <n-input
                v-model:value="controlDescription"
                type="textarea"
                :autosize="{ minRows: 2, maxRows: 5 }"
              />
            </n-form-item>
            <n-form-item :label="$t('page.research.entryStep')" required>
              <n-select v-model:value="controlEntryStepKey" :options="controlEntryOptions" />
            </n-form-item>
            <div class="mb-2 flex items-center justify-between gap-3">
              <div>
                <div class="aira-type-card-title">
                  {{ $t("page.research.controlSteps") }}
                </div>
                <div class="aira-type-meta mt-1">
                  {{ $t("page.research.controlStepsHint") }}
                </div>
              </div>
              <n-button size="small" secondary @click="addControlStep">
                {{ $t("page.research.addControlStep") }}
              </n-button>
            </div>
            <div class="space-y-3">
              <section
                v-for="(step, index) in controlSteps"
                :key="index"
                class="control-step"
              >
                <div class="mb-3 flex items-center justify-between gap-3">
                  <strong>{{ $t("page.research.controlStepNumber", { number: index + 1 }) }}</strong>
                  <n-button
                    quaternary
                    size="small"
                    :disabled="controlSteps.length === 1"
                    @click="removeControlStep(index)"
                  >
                    {{ $t("common.delete") }}
                  </n-button>
                </div>
                <div class="control-grid">
                  <n-form-item :label="$t('page.research.stepKey')" required>
                    <n-input
                      :value="step.key"
                      placeholder="observe"
                      @update:value="value => updateControlStepKey(index, value)"
                    />
                  </n-form-item>
                  <n-form-item :label="$t('page.research.instrumentCommand')" required>
                    <n-select
                      v-model:value="step.commandId"
                      :options="controlCommandOptions"
                      :placeholder="$t('page.research.selectInstrumentCommand')"
                    />
                  </n-form-item>
                </div>
                <n-form-item
                  :label="$t('page.research.instrumentArguments')"
                  required
                  :validation-status="parseJsonObject(step.argumentsText) ? undefined : 'error'"
                >
                  <n-input
                    v-model:value="step.argumentsText"
                    type="textarea"
                    :autosize="{ minRows: 2, maxRows: 8 }"
                    class="font-mono"
                  />
                </n-form-item>
                <div class="control-grid">
                  <n-form-item :label="$t('page.research.onSuccess')" required>
                    <n-select v-model:value="step.onTrue" :options="controlTargetOptions" />
                  </n-form-item>
                  <n-form-item v-if="controlMode === 'feedback_loop'" :label="$t('page.research.branchOnResult')">
                    <n-switch v-model:value="step.conditionEnabled" />
                  </n-form-item>
                </div>
                <div v-if="controlMode === 'feedback_loop' && step.conditionEnabled" class="control-condition">
                  <n-form-item :label="$t('page.research.resultPath')" required>
                    <n-input v-model:value="step.conditionPath" placeholder="reading.temperature" />
                  </n-form-item>
                  <n-form-item :label="$t('page.research.comparison')" required>
                    <n-select
                      v-model:value="step.conditionOperator"
                      :options="[
                        { label: '=', value: 'eq' },
                        { label: '≠', value: 'ne' },
                        { label: '<', value: 'lt' },
                        { label: '≤', value: 'lte' },
                        { label: '>', value: 'gt' },
                        { label: '≥', value: 'gte' },
                        { label: $t('page.research.inList'), value: 'in' },
                        { label: $t('page.research.exists'), value: 'exists' },
                      ]"
                    />
                  </n-form-item>
                  <n-form-item :label="$t('page.research.comparisonValue')" required>
                    <n-input v-model:value="step.conditionValueText" class="font-mono" />
                  </n-form-item>
                  <n-form-item :label="$t('page.research.otherwise')" required>
                    <n-select v-model:value="step.onFalse" :options="controlTargetOptions" />
                  </n-form-item>
                </div>
              </section>
            </div>
          </n-form>
        </n-tab-pane>

        <n-tab-pane name="wait" :tab="$t('page.research.waitEventAction')">
          <n-alert type="warning" class="mb-4">
            {{ $t("page.research.waitEventHint") }}
          </n-alert>
          <n-form label-placement="top">
            <n-form-item :label="$t('page.research.waitFor')" required>
              <n-select v-model:value="waitPreset" :options="waitPresetOptions" />
            </n-form-item>
            <n-form-item :label="$t('page.research.actionTitle')" required>
              <n-input
                v-model:value="waitDraft.title"
                :placeholder="$t('page.research.waitTitlePlaceholder')"
              />
            </n-form-item>
            <n-form-item :label="$t('page.research.actionDescription')">
              <n-input
                v-model:value="waitDraft.description"
                type="textarea"
                :autosize="{ minRows: 2, maxRows: 6 }"
              />
            </n-form-item>
            <n-form-item :label="$t('page.research.dueOptional')">
              <n-date-picker
                v-model:value="waitDueAt"
                type="datetime"
                clearable
                :is-date-disabled="disablePastDate"
              />
            </n-form-item>
          </n-form>
        </n-tab-pane>
      </n-tabs>
    </template>

    <template v-else>
      <n-alert type="info">
        {{ $t("page.research.digitalActionPreviewHint") }}
      </n-alert>
      <div class="digital-preview mt-4">
        <div class="aira-type-eyebrow">
          {{ $t("page.research.saveDestination") }}
        </div>
        <h3 class="aira-type-card-title mb-0 mt-1">
          {{ preview.destination.task.title }} ·
          {{ $t("page.research.runNumber", { number: preview.destination.run.number }) }}
        </h3>
        <template v-if="previewKind === 'tool'">
          <div class="mt-4 flex flex-wrap items-center gap-2">
            <n-tag type="info" round>
              {{ preview.tool?.name }}
            </n-tag>
            <span class="aira-type-meta">v{{ preview.tool?.version }}</span>
          </div>
          <template v-if="preview.command.tool_key === 'aira.specialist'">
            <dl class="digital-preview__facts mt-3">
              <div>
                <dt>{{ $t("page.research.specialistRole") }}</dt>
                <dd>{{ specialistRoleLabel(String(preview.command.arguments?.role || "")) }}</dd>
              </div>
              <div>
                <dt>{{ $t("page.research.specialistContext") }}</dt>
                <dd class="font-mono">
                  {{ shortDigest(String(preview.command.specialist_context?.digest || "")) }}
                </dd>
              </div>
            </dl>
            <p class="aira-type-body aira-text-secondary mb-0 mt-3">
              {{ String(preview.command.arguments?.question || "") }}
            </p>
            <n-collapse class="mt-3">
              <n-collapse-item
                :title="$t('page.research.specialistContextSources', { count: preview.command.specialist_context?.sources?.length || 0 })"
                name="specialist-context"
              >
                <p v-if="specialistCoverage.omitted || specialistCoverage.truncated" class="aira-type-meta">
                  {{ $t("page.research.specialistContextCoverage", specialistCoverage) }}
                </p>
                <div class="space-y-2">
                  <div
                    v-for="source in (preview.command.specialist_context?.sources || [])"
                    :key="String(source.ref)"
                    class="specialist-context-source"
                  >
                    <strong class="aira-type-label">{{ String(source.title) }}</strong>
                    <div class="aira-type-meta mt-1 font-mono">
                      {{ String(source.ref) }}
                    </div>
                    <pre>{{ String(source.content) }}</pre>
                  </div>
                </div>
              </n-collapse-item>
            </n-collapse>
            <n-alert type="warning" class="mt-3">
              {{ $t("page.research.specialistPreviewBoundary") }}
            </n-alert>
          </template>
          <template v-else>
            <pre class="mt-3">{{ JSON.stringify(preview.command.arguments, null, 2) }}</pre>
            <p class="aira-type-meta mb-0 mt-2">
              {{ $t("page.research.toolResultsStayDraft") }}
            </p>
          </template>
        </template>
        <template v-else-if="previewKind === 'instrument'">
          <div class="mt-4 flex flex-wrap items-center gap-2">
            <n-tag type="warning" round>
              {{ preview.instrument?.name }}
            </n-tag>
            <n-tag :type="instrumentRiskType(preview.instrument?.risk)" size="small" round>
              {{ instrumentRiskLabel(preview.instrument?.risk) }}
            </n-tag>
          </div>
          <dl class="digital-preview__facts mt-3">
            <div>
              <dt>{{ $t("page.research.equipment") }}</dt>
              <dd>{{ preview.instrument?.resource.name }} · {{ preview.instrument?.resource.code }}</dd>
            </div>
            <div>
              <dt>{{ $t("page.research.gateway") }}</dt>
              <dd>{{ preview.instrument?.gateway.name }}</dd>
            </div>
            <div>
              <dt>{{ $t("page.research.approvedBooking") }}</dt>
              <dd>
                {{ formatBooking(preview.instrument?.booking) }}
              </dd>
            </div>
            <div>
              <dt>{{ $t("page.research.deviceConfirmation") }}</dt>
              <dd>
                {{ preview.instrument?.device_confirmation_required ? $t("page.research.deviceConfirmationRequired") : $t("page.research.deviceConfirmationNotRequired") }}
              </dd>
            </div>
            <div>
              <dt>{{ $t("page.resourceLibrary.safetyContract") }}</dt>
              <dd>{{ safetyContractSummary(preview.instrument?.safety_contract) }}</dd>
            </div>
          </dl>
          <pre class="mt-3">{{ JSON.stringify(preview.command.arguments, null, 2) }}</pre>
          <n-alert type="warning" class="mt-3">
            {{ $t("page.research.instrumentNoAutomaticRetry") }}
          </n-alert>
        </template>
        <template v-else-if="previewKind === 'control'">
          <div class="mt-4 flex flex-wrap items-center gap-2">
            <n-tag type="warning" round>
              {{ $t("page.research.instrumentControl") }}
            </n-tag>
            <n-tag size="small" round>
              {{ preview.instrument_control?.mode === "feedback_loop" ? $t("page.research.feedbackLoop") : $t("page.research.boundedSequence") }}
            </n-tag>
            <n-tag :type="instrumentRiskType(preview.instrument_control?.highest_risk)" size="small" round>
              {{ instrumentRiskLabel(preview.instrument_control?.highest_risk) }}
            </n-tag>
          </div>
          <dl class="digital-preview__facts mt-3">
            <div>
              <dt>{{ $t("page.research.equipment") }}</dt>
              <dd>{{ preview.instrument_control?.resource?.name }} · {{ preview.instrument_control?.resource?.code }}</dd>
            </div>
            <div>
              <dt>{{ $t("page.research.gateway") }}</dt>
              <dd>{{ preview.instrument_control?.gateway?.name }}</dd>
            </div>
            <div>
              <dt>{{ $t("page.research.controlSteps") }}</dt>
              <dd>{{ preview.instrument_control?.step_count }} / {{ preview.instrument_control?.max_steps }}</dd>
            </div>
            <div>
              <dt>{{ $t("page.research.maximumDurationMinutes") }}</dt>
              <dd>{{ Math.round(Number(preview.instrument_control?.max_duration_seconds || 0) / 60) }}</dd>
            </div>
          </dl>
          <ol class="control-preview-steps mt-3">
            <li
              v-for="step in (preview.command.program?.steps || [])"
              :key="String(step.key)"
            >
              <div class="flex flex-wrap items-center gap-2">
                <strong>{{ String(step.key) }}</strong>
                <span>{{ String(step.command?.name || step.command?.command_key) }}</span>
                <n-tag :type="instrumentRiskType(step.command?.risk)" size="small" round>
                  {{ instrumentRiskLabel(step.command?.risk) }}
                </n-tag>
              </div>
              <div class="aira-type-meta mt-1">
                → {{ String(step.transition?.on_true) }}<template v-if="step.transition?.condition">
                  / {{ String(step.transition?.on_false) }}
                </template>
              </div>
            </li>
          </ol>
          <n-alert type="warning" class="mt-3">
            {{ $t("page.research.instrumentControlPreviewWarning") }}
          </n-alert>
        </template>
        <template v-else>
          <div class="mt-4 flex flex-wrap items-center gap-2">
            <n-tag type="warning" round>
              {{ $t("page.research.waitEventAction") }}
            </n-tag>
            <span class="aira-type-meta">{{ String(preview.command.expected_event_type) }}</span>
          </div>
          <dl class="digital-preview__facts mt-3">
            <div>
              <dt>{{ $t("page.research.eventKey") }}</dt>
              <dd>{{ String(preview.command.event_key) }}</dd>
            </div>
            <div v-if="preview.command.due_at">
              <dt>{{ $t("page.research.due") }}</dt>
              <dd><n-time :time="new Date(String(preview.command.due_at))" /></dd>
            </div>
          </dl>
          <p class="aira-type-meta mb-0 mt-3">
            {{ $t("page.research.waitPausesRun") }}
          </p>
        </template>
      </div>
    </template>

    <template #footer>
      <div class="flex justify-end gap-2">
        <n-button @click="preview ? (preview = null) : (visible = false)">
          {{ preview ? $t("page.research.backToEdit") : $t("common.cancel") }}
        </n-button>
        <n-button
          v-if="!preview"
          type="primary"
          :disabled="!canPreview"
          :loading="submitting"
          @click="previewAction"
        >
          {{ $t("page.research.previewAction") }}
        </n-button>
        <n-button v-else type="primary" :loading="submitting" @click="confirmAction">
          {{ $t("page.research.confirmDigitalAction") }}
        </n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import type {
  AiraInstrumentControlDraftResponse,
  DigitalActionPreview,
  InstrumentActionDraft,
  InstrumentControlDraft,
  InstrumentControlStepDraft,
  ResearchInstrumentCommandOption,
  ResearchSpecialistRole,
  ResearchToolDefinition,
  ToolActionDraft,
  WaitActionDraft,
} from "@/service/api/research-actions"
import type { EquipmentBooking } from "@/service/api/resources"
import {
  createInstrumentAction,
  createInstrumentControlSession,
  createToolAction,
  createWaitAction,
  draftInstrumentControlWithAira,
  fetchResearchInstrumentCommands,
  fetchResearchTools,
  previewInstrumentAction,
  previewInstrumentControlSession,
  previewToolAction,
  previewWaitAction,
} from "@/service/api/research-actions"
import { $t } from "@airalogy/shared/locales"
import { nanoid } from "nanoid"

const props = defineProps<{ taskId: string, aiAvailable?: boolean }>()
const emit = defineEmits<{ created: [] }>()

type Mode = "tool" | "instrument" | "control" | "wait"
type WaitPreset = "data_asset" | "research_file" | "external_service"
interface ControlStepEditor {
  key: string
  commandId: string
  argumentsText: string
  onTrue: string
  conditionEnabled: boolean
  conditionPath: string
  conditionOperator: "eq" | "ne" | "lt" | "lte" | "gt" | "gte" | "in" | "exists"
  conditionValueText: string
  onFalse: string
}

const visible = ref(false)
const mode = ref<Mode>("tool")
const previewKind = ref<Mode>("tool")
const preview = ref<DigitalActionPreview<any> | null>(null)
const specialistCoverage = computed(() => {
  const coverage = (preview.value?.command.specialist_context?.coverage || {}) as Record<string, { omitted: number, truncated: number }>
  return Object.values(coverage).reduce((total, item) => ({
    omitted: total.omitted + item.omitted,
    truncated: total.truncated + item.truncated,
  }), { omitted: 0, truncated: 0 })
})
const submitting = ref(false)
const toolsLoading = ref(false)
const instrumentsLoading = ref(false)
const tools = ref<ResearchToolDefinition[]>([])
const instruments = ref<ResearchInstrumentCommandOption[]>([])
const toolQuery = ref("")
const toolLimit = ref(20)
const toolDoi = ref("")
const toolArgumentsText = ref("{}")
const specialistRole = ref<ResearchSpecialistRole>("literature_analyst")
const specialistQuestion = ref("")
const specialistDeliverable = ref("")
const waitPreset = ref<WaitPreset>("data_asset")
const waitDueAt = ref<number | null>(null)
const instrumentArgumentsText = ref("{}")
const controlMode = ref<InstrumentControlDraft["mode"]>("bounded_sequence")
const controlTitle = ref("")
const controlDescription = ref("")
const controlBookingId = ref("")
const controlEntryStepKey = ref("")
const controlMaxSteps = ref(8)
const controlDurationMinutes = ref(60)
const controlIdempotencyKey = ref("")
const controlSteps = ref<ControlStepEditor[]>([])
const airaControlInstruction = ref("")
const airaStepTemplateLimit = ref(6)
const airaControlDrafting = ref(false)
const airaControlDraftResult = ref<AiraInstrumentControlDraftResponse | null>(null)

const toolDraft = reactive<ToolActionDraft>({
  tool_key: "",
  arguments: {},
  title: "",
  description: "",
  idempotency_key: "",
})
const waitDraft = reactive<WaitActionDraft>({
  title: "",
  description: "",
  event_key: "",
  expected_event_type: "",
  payload_schema: {},
  due_at: null,
  idempotency_key: "",
})
const instrumentDraft = reactive<InstrumentActionDraft>({
  command_id: "",
  equipment_booking_id: "",
  arguments: {},
  title: "",
  description: "",
  idempotency_key: "",
})

const waitDefinitions: Record<WaitPreset, { eventType: string, schema: Record<string, unknown> }>
  = {
    data_asset: {
      eventType: "data_asset.ready",
      schema: {
        type: "object",
        additionalProperties: false,
        required: ["data_asset_id", "version"],
        properties: {
          data_asset_id: { type: "string", minLength: 1 },
          version: { type: "integer", minimum: 1 },
        },
      },
    },
    research_file: {
      eventType: "research_file.received",
      schema: {
        type: "object",
        additionalProperties: false,
        required: ["file_id"],
        properties: {
          file_id: { type: "string", minLength: 1 },
          checksum: { type: "string" },
        },
      },
    },
    external_service: {
      eventType: "external_service.finished",
      schema: {
        type: "object",
        additionalProperties: false,
        required: ["result_uri", "status"],
        properties: {
          result_uri: { type: "string", minLength: 1 },
          status: { type: "string", enum: ["completed", "failed"] },
        },
      },
    },
  }

const toolOptions = computed(() =>
  tools.value.map(item => ({
    label: `${item.name} · v${item.version}`,
    value: item.key,
    disabled: !item.available,
  })),
)
const selectedTool = computed(() => tools.value.find(item => item.key === toolDraft.tool_key))
const toolArgumentKind = computed<"search" | "doi" | "specialist" | "json">(() => {
  if (["knowledge.search", "literature.search"].includes(toolDraft.tool_key))
    return "search"
  if (toolDraft.tool_key === "literature.resolve_doi")
    return "doi"
  if (toolDraft.tool_key === "aira.specialist")
    return "specialist"
  return "json"
})
const genericToolArguments = computed(() => parseJsonObject(toolArgumentsText.value))
const specialistRoleOptions = computed(() => [
  "literature_analyst",
  "experimental_designer",
  "data_analyst",
  "research_critic",
].map(value => ({
  value,
  label: specialistRoleLabel(value),
})))
const toolArguments = computed<Record<string, unknown> | null>(() => {
  if (toolArgumentKind.value === "search") {
    return toolQuery.value.trim()
      ? { query: toolQuery.value.trim(), limit: toolLimit.value }
      : null
  }
  if (toolArgumentKind.value === "doi")
    return toolDoi.value.trim() ? { doi: toolDoi.value.trim() } : null
  if (toolArgumentKind.value === "specialist") {
    return specialistQuestion.value.trim()
      ? {
          role: specialistRole.value,
          question: specialistQuestion.value.trim(),
          deliverable: specialistDeliverable.value.trim(),
        }
      : null
  }
  return genericToolArguments.value
})
const selectedInstrument = computed(() =>
  instruments.value.find(item => item.id === instrumentDraft.command_id),
)
const instrumentOptions = computed(() =>
  instruments.value.map(item => ({
    label: `${item.name} · ${item.resource.name} · v${item.command_version}`,
    value: item.id,
    disabled: !item.bookings.length,
  })),
)
const bookingOptions = computed(() =>
  (selectedInstrument.value?.bookings || []).map(item => ({
    label: formatBooking(item),
    value: item.id,
  })),
)
const controlBookingOptions = computed(() => {
  const bookings = new Map<string, EquipmentBooking>()
  for (const instrument of instruments.value) {
    for (const booking of instrument.bookings)
      bookings.set(booking.id, booking)
  }
  return [...bookings.values()].map(item => ({
    label: formatBooking(item),
    value: item.id,
  }))
})
const controlCommandOptions = computed(() =>
  instruments.value
    .filter(item => item.bookings.some(booking => booking.id === controlBookingId.value))
    .map(item => ({
      label: `${item.name} · ${item.resource.name} · v${item.command_version}`,
      value: item.id,
    })),
)
const controlTargetOptions = computed(() => [
  ...controlSteps.value
    .filter(item => item.key.trim())
    .map(item => ({ label: item.key.trim(), value: item.key.trim() })),
  { label: $t("page.research.controlComplete"), value: "complete" },
  { label: $t("page.research.controlPause"), value: "pause" },
])
const controlEntryOptions = computed(() =>
  controlSteps.value
    .filter(item => item.key.trim())
    .map(item => ({ label: item.key.trim(), value: item.key.trim() })),
)
const instrumentArguments = computed<Record<string, unknown> | null>(() => {
  try {
    const value = JSON.parse(instrumentArgumentsText.value)
    return value && typeof value === "object" && !Array.isArray(value) ? value : null
  }
  catch {
    return null
  }
})
const instrumentArgumentsValid = computed(() => instrumentArguments.value !== null)
const controlPayload = computed<InstrumentControlDraft | null>(() => {
  const keys = controlSteps.value.map(item => item.key.trim().toLowerCase())
  if (
    !controlTitle.value.trim()
    || !controlBookingId.value
    || !controlEntryStepKey.value
    || !controlSteps.value.length
    || new Set(keys).size !== keys.length
    || keys.some(key => !/^[a-z][a-z0-9_-]{0,63}$/.test(key))
  ) {
    return null
  }
  const steps: InstrumentControlStepDraft[] = []
  for (const item of controlSteps.value) {
    const argumentsValue = parseJsonObject(item.argumentsText)
    const allowedTargets = new Set([...keys, "complete", "pause"])
    if (!item.commandId || !argumentsValue || !allowedTargets.has(item.onTrue)) {
      return null
    }
    let condition = null
    if (item.conditionEnabled) {
      const value = parseJsonValue(item.conditionValueText)
      if (
        controlMode.value !== "feedback_loop"
        || !/^[a-z][\w-]*(?:\.[a-z][\w-]*){0,7}$/i.test(item.conditionPath)
        || value === undefined
        || !allowedTargets.has(item.onFalse)
      ) {
        return null
      }
      condition = {
        path: item.conditionPath,
        operator: item.conditionOperator,
        value,
      }
    }
    steps.push({
      key: item.key.trim().toLowerCase(),
      command_id: item.commandId,
      arguments: argumentsValue,
      transition: {
        condition,
        on_true: item.onTrue,
        on_false: condition ? item.onFalse : null,
      },
    })
  }
  return {
    mode: controlMode.value,
    title: controlTitle.value.trim(),
    description: controlDescription.value.trim(),
    equipment_booking_id: controlBookingId.value,
    entry_step_key: controlEntryStepKey.value,
    steps,
    max_steps: controlMode.value === "bounded_sequence" ? steps.length : controlMaxSteps.value,
    max_duration_seconds: controlDurationMinutes.value * 60,
    idempotency_key: controlIdempotencyKey.value,
  }
})
const waitPresetOptions = computed(() => [
  { label: $t("page.research.waitDataAsset"), value: "data_asset" },
  { label: $t("page.research.waitResearchFile"), value: "research_file" },
  { label: $t("page.research.waitExternalService"), value: "external_service" },
])
const canPreview = computed(() =>
  mode.value === "tool"
    ? Boolean(toolDraft.tool_key && selectedTool.value?.available && toolArguments.value)
    : mode.value === "instrument"
      ? Boolean(
        instrumentDraft.command_id
        && instrumentDraft.equipment_booking_id
        && instrumentArgumentsValid.value,
      )
      : mode.value === "control"
        ? Boolean(controlPayload.value)
        : Boolean(waitDraft.title.trim() && (!waitDueAt.value || waitDueAt.value > Date.now())),
)

async function loadTools() {
  toolsLoading.value = true
  try {
    tools.value = (await fetchResearchTools(props.taskId)).tools
    toolDraft.tool_key ||= tools.value.find(item => item.available)?.key || ""
  }
  finally {
    toolsLoading.value = false
  }
}

async function loadInstruments() {
  instrumentsLoading.value = true
  try {
    instruments.value = (await fetchResearchInstrumentCommands(props.taskId)).items
    instrumentDraft.command_id ||= instruments.value.find(item => item.bookings.length)?.id || ""
    selectDefaultBooking()
    controlBookingId.value ||= controlBookingOptions.value[0]?.value || ""
    if (!controlSteps.value.length)
      addControlStep()
  }
  finally {
    instrumentsLoading.value = false
  }
}

function parseJsonValue(text: string): unknown | undefined {
  try {
    return JSON.parse(text)
  }
  catch {
    return undefined
  }
}

function parseJsonObject(text: string): Record<string, unknown> | null {
  const value = parseJsonValue(text)
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null
}

function specialistRoleLabel(role: string) {
  const knownRoles = new Set([
    "literature_analyst",
    "experimental_designer",
    "data_analyst",
    "research_critic",
  ])
  return knownRoles.has(role)
    ? $t(`page.research.specialistRoles.${role}` as I18n.I18nKey)
    : role
}

function shortDigest(value: string) {
  return value ? `${value.slice(0, 12)}…` : "—"
}

function addControlStep() {
  const number = controlSteps.value.length + 1
  const key = `step_${number}`
  const previous = controlSteps.value.at(-1)
  if (previous && previous.onTrue === "complete")
    previous.onTrue = key
  controlSteps.value.push({
    key,
    commandId: controlCommandOptions.value[0]?.value || "",
    argumentsText: "{}",
    onTrue: "complete",
    conditionEnabled: false,
    conditionPath: "value",
    conditionOperator: "gte",
    conditionValueText: "0",
    onFalse: "pause",
  })
  controlEntryStepKey.value ||= key
  controlMaxSteps.value = Math.max(controlMaxSteps.value, controlSteps.value.length)
}

function removeControlStep(index: number) {
  const removed = controlSteps.value[index]
  controlSteps.value.splice(index, 1)
  if (controlEntryStepKey.value === removed?.key)
    controlEntryStepKey.value = controlSteps.value[0]?.key || ""
  for (const step of controlSteps.value) {
    if (step.onTrue === removed?.key)
      step.onTrue = "complete"
    if (step.onFalse === removed?.key)
      step.onFalse = "pause"
  }
  controlMaxSteps.value = Math.max(controlSteps.value.length, controlMaxSteps.value)
}

function updateControlStepKey(index: number, value: string) {
  const step = controlSteps.value[index]
  if (!step)
    return
  const previous = step.key
  const normalized = value.trim().toLowerCase()
  step.key = normalized
  if (controlEntryStepKey.value === previous)
    controlEntryStepKey.value = normalized
  for (const item of controlSteps.value) {
    if (item.onTrue === previous)
      item.onTrue = normalized
    if (item.onFalse === previous)
      item.onFalse = normalized
  }
}

async function handleAiraControlDraft() {
  if (!props.aiAvailable || !controlBookingId.value || !airaControlInstruction.value.trim())
    return
  const maxStepTemplates = controlMode.value === "feedback_loop"
    ? Math.min(airaStepTemplateLimit.value, controlMaxSteps.value)
    : airaStepTemplateLimit.value
  airaControlDrafting.value = true
  try {
    const result = await draftInstrumentControlWithAira(props.taskId, {
      instruction: airaControlInstruction.value.trim(),
      mode: controlMode.value,
      equipment_booking_id: controlBookingId.value,
      max_step_templates: maxStepTemplates,
      max_steps: controlMode.value === "feedback_loop"
        ? controlMaxSteps.value
        : maxStepTemplates,
      max_duration_seconds: controlDurationMinutes.value * 60,
    })
    controlMode.value = result.draft.mode
    controlTitle.value = result.draft.title
    controlDescription.value = result.draft.description
    controlBookingId.value = result.draft.equipment_booking_id
    controlEntryStepKey.value = result.draft.entry_step_key
    controlMaxSteps.value = result.draft.max_steps
    controlDurationMinutes.value = Math.ceil(result.draft.max_duration_seconds / 60)
    controlIdempotencyKey.value = result.draft.idempotency_key
    controlSteps.value = result.draft.steps.map(step => ({
      key: step.key,
      commandId: step.command_id,
      argumentsText: JSON.stringify(step.arguments, null, 2),
      onTrue: step.transition.on_true,
      conditionEnabled: Boolean(step.transition.condition),
      conditionPath: step.transition.condition?.path || "value",
      conditionOperator: step.transition.condition?.operator || "gte",
      conditionValueText: JSON.stringify(step.transition.condition?.value ?? 0),
      onFalse: step.transition.on_false || "pause",
    }))
    airaControlDraftResult.value = result
    window.$message?.success($t("page.research.controlDraftReady"))
  }
  finally {
    airaControlDrafting.value = false
  }
}

function selectDefaultBooking() {
  const bookings = selectedInstrument.value?.bookings || []
  if (!bookings.some(item => item.id === instrumentDraft.equipment_booking_id))
    instrumentDraft.equipment_booking_id = bookings[0]?.id || ""
}

function formatBooking(booking?: EquipmentBooking) {
  if (!booking)
    return "—"
  return `${new Date(booking.starts_at).toLocaleString()} – ${new Date(booking.ends_at).toLocaleString()}`
}

function safetyContractSummary(contract?: ResearchInstrumentCommandOption["safety_contract"]) {
  if (!contract)
    return "—"
  const parts = [...contract.required_interlocks]
  if (contract.operator_presence_required)
    parts.push($t("page.resourceLibrary.operatorPresenceRequired"))
  if (contract.emergency_stop_required)
    parts.push($t("page.resourceLibrary.emergencyStopRequired"))
  return parts.join(" · ") || "—"
}

function instrumentRiskType(risk?: ResearchInstrumentCommandOption["risk"]) {
  if (risk === "high")
    return "error"
  if (risk === "medium")
    return "warning"
  return "info"
}

function instrumentRiskLabel(risk?: ResearchInstrumentCommandOption["risk"]) {
  return risk
    ? $t(`page.resourceLibrary.risk.${risk}` as I18n.I18nKey)
    : "—"
}

function applyWaitPreset() {
  const definition = waitDefinitions[waitPreset.value]
  waitDraft.expected_event_type = definition.eventType
  waitDraft.payload_schema = definition.schema
}

function open() {
  visible.value = true
  if (!tools.value.length)
    void loadTools()
  if (!instruments.value.length)
    void loadInstruments()
}

function reset() {
  preview.value = null
  mode.value = "tool"
  previewKind.value = "tool"
  toolQuery.value = ""
  toolLimit.value = 20
  toolDoi.value = ""
  toolArgumentsText.value = "{}"
  specialistRole.value = "literature_analyst"
  specialistQuestion.value = ""
  specialistDeliverable.value = ""
  toolDraft.title = ""
  toolDraft.description = ""
  toolDraft.idempotency_key = ""
  waitPreset.value = "data_asset"
  waitDueAt.value = null
  waitDraft.title = ""
  waitDraft.description = ""
  waitDraft.event_key = ""
  waitDraft.idempotency_key = ""
  waitDraft.due_at = null
  instrumentDraft.command_id = ""
  instrumentDraft.equipment_booking_id = ""
  instrumentDraft.arguments = {}
  instrumentDraft.title = ""
  instrumentDraft.description = ""
  instrumentDraft.idempotency_key = ""
  instrumentArgumentsText.value = "{}"
  controlMode.value = "bounded_sequence"
  controlTitle.value = ""
  controlDescription.value = ""
  controlBookingId.value = ""
  controlEntryStepKey.value = ""
  controlMaxSteps.value = 8
  controlDurationMinutes.value = 60
  controlIdempotencyKey.value = ""
  controlSteps.value = []
  airaControlInstruction.value = ""
  airaStepTemplateLimit.value = 6
  airaControlDrafting.value = false
  airaControlDraftResult.value = null
  applyWaitPreset()
}

function disablePastDate(timestamp: number) {
  return timestamp < new Date().setHours(0, 0, 0, 0)
}

async function previewAction() {
  if (!canPreview.value)
    return
  submitting.value = true
  previewKind.value = mode.value
  try {
    if (mode.value === "tool") {
      toolDraft.arguments = toolArguments.value || {}
      toolDraft.idempotency_key ||= `tool-${nanoid(16)}`
      preview.value = await previewToolAction(props.taskId, { ...toolDraft })
    }
    else if (mode.value === "instrument") {
      instrumentDraft.arguments = instrumentArguments.value || {}
      instrumentDraft.idempotency_key ||= `instrument-${nanoid(16)}`
      preview.value = await previewInstrumentAction(props.taskId, { ...instrumentDraft })
    }
    else if (mode.value === "control") {
      controlIdempotencyKey.value ||= `instrument-control-${nanoid(16)}`
      const payload = controlPayload.value
      if (!payload)
        return
      preview.value = await previewInstrumentControlSession(props.taskId, payload)
    }
    else {
      applyWaitPreset()
      waitDraft.event_key ||= `research.wait.${nanoid(16)}`
      waitDraft.idempotency_key ||= `wait-${nanoid(16)}`
      waitDraft.due_at = waitDueAt.value ? new Date(waitDueAt.value).toISOString() : null
      preview.value = await previewWaitAction(props.taskId, { ...waitDraft })
    }
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
    if (previewKind.value === "tool") {
      await createToolAction(props.taskId, {
        ...toolDraft,
        preview_digest: preview.value.preview_digest,
      })
    }
    else if (previewKind.value === "instrument") {
      await createInstrumentAction(props.taskId, {
        ...instrumentDraft,
        preview_digest: preview.value.preview_digest,
      })
    }
    else if (previewKind.value === "control") {
      const payload = controlPayload.value
      if (!payload)
        return
      await createInstrumentControlSession(props.taskId, {
        ...payload,
        preview_digest: preview.value.preview_digest,
      })
    }
    else {
      await createWaitAction(props.taskId, {
        ...waitDraft,
        preview_digest: preview.value.preview_digest,
      })
    }
    visible.value = false
    window.$message?.success($t("page.research.digitalActionCreated"))
    emit("created")
  }
  finally {
    submitting.value = false
  }
}

watch(waitPreset, applyWaitPreset, { immediate: true })
watch(() => instrumentDraft.command_id, selectDefaultBooking)
watch(controlBookingId, () => {
  const allowed = new Set(controlCommandOptions.value.map(item => item.value))
  for (const step of controlSteps.value) {
    if (!allowed.has(step.commandId))
      step.commandId = controlCommandOptions.value[0]?.value || ""
  }
})
watch(controlMode, (value) => {
  if (value === "bounded_sequence") {
    for (const step of controlSteps.value)
      step.conditionEnabled = false
  }
})
</script>

<style scoped>
.digital-preview {
  border: 1px solid rgb(226 232 240);
  border-radius: 0.875rem;
  background: rgb(248 250 252);
  padding: 1rem;
}

.digital-preview__facts {
  display: grid;
  gap: 0.625rem;
}

.digital-preview__facts > div {
  display: grid;
  grid-template-columns: minmax(7rem, auto) minmax(0, 1fr);
  gap: 0.75rem;
}

.digital-preview__facts dt {
  color: rgb(100 116 139);
  font-size: 0.75rem;
}

.digital-preview__facts dd {
  min-width: 0;
  overflow-wrap: anywhere;
  font-size: 0.8125rem;
}

.specialist-context-source {
  border: 1px solid rgb(226 232 240);
  border-radius: 0.625rem;
  background: white;
  padding: 0.75rem;
}

.specialist-context-source pre {
  max-height: 12rem;
  overflow: auto;
  margin: 0.5rem 0 0;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  color: rgb(71 85 105);
  font-size: 0.75rem;
  line-height: 1.55;
}

.control-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 1rem;
}

.aira-control-draft {
  border: 1px solid rgb(191 219 254);
  border-radius: 0.875rem;
  background: linear-gradient(145deg, rgb(239 246 255), rgb(248 250 252));
  padding: 1rem;
}

.control-step {
  border: 1px solid rgb(226 232 240);
  border-radius: 0.75rem;
  background: rgb(248 250 252);
  padding: 0.875rem;
}

.control-condition {
  display: grid;
  grid-template-columns: 1.25fr 0.75fr 1fr 1fr;
  gap: 0 0.75rem;
  border-top: 1px dashed rgb(203 213 225);
  padding-top: 0.75rem;
}

.control-preview-steps {
  display: grid;
  gap: 0.5rem;
  padding-left: 1.5rem;
}

.control-preview-steps li {
  border: 1px solid rgb(226 232 240);
  border-radius: 0.625rem;
  background: white;
  padding: 0.625rem 0.75rem;
}

@media (max-width: 42rem) {
  .control-grid,
  .control-grid--limits,
  .control-condition {
    grid-template-columns: minmax(0, 1fr);
  }
}

:global(.research-digital-modal) {
  width: min(54rem, calc(100vw - 2rem));
}
</style>
