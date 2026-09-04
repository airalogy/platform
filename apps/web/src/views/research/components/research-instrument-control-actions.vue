<template>
  <div v-if="isCurrent" class="flex flex-wrap justify-end gap-2">
    <n-button
      v-if="canResume"
      size="small"
      type="primary"
      secondary
      @click="open('resume')"
    >
      {{ $t("page.research.reviewAndResumeControl") }}
    </n-button>
    <n-button
      v-if="canStop"
      size="small"
      type="error"
      secondary
      @click="open('stop')"
    >
      {{ $t("page.research.stopControlSession") }}
    </n-button>
  </div>

  <n-modal
    v-model:show="visible"
    preset="card"
    class="research-instrument-control-decision-modal"
    :title="mode === 'resume' ? $t('page.research.reviewAndResumeControl') : $t('page.research.stopControlSession')"
    :mask-closable="false"
    @after-leave="reset"
  >
    <template v-if="!preview">
      <n-alert :type="mode === 'resume' ? 'warning' : 'error'">
        {{ mode === "resume" ? session.pause_reason : $t("page.research.instrumentControlStopHint") }}
      </n-alert>
      <dl v-if="mode === 'resume'" class="control-decision-facts mt-4">
        <div>
          <dt>{{ $t("page.research.pendingStep") }}</dt>
          <dd>{{ session.pending_step_key }}</dd>
        </div>
        <div>
          <dt>{{ $t("page.research.controlProgress") }}</dt>
          <dd>{{ session.executed_steps }} / {{ session.max_steps }}</dd>
        </div>
      </dl>
      <n-form label-placement="top" class="mt-4">
        <n-form-item :label="mode === 'resume' ? $t('page.research.reviewReason') : $t('page.research.stopReason')" required>
          <n-input
            v-model:value="reason"
            type="textarea"
            :autosize="{ minRows: 3, maxRows: 8 }"
          />
        </n-form-item>
      </n-form>
    </template>
    <template v-else>
      <n-alert :type="mode === 'resume' ? 'warning' : 'error'">
        {{ mode === "resume" ? $t("page.research.instrumentControlResumeConfirm") : $t("page.research.instrumentControlStopConfirm") }}
      </n-alert>
      <div class="control-decision-preview mt-4">
        <div class="aira-type-eyebrow">
          {{ $t("page.research.effects") }}
        </div>
        <ul class="mb-0 mt-2 pl-5">
          <li v-for="effect in preview.effects || []" :key="effect">
            {{ effect }}
          </li>
        </ul>
      </div>
      <div v-if="mode === 'resume' && preview.pending_step" class="control-decision-preview mt-3">
        <div class="flex flex-wrap items-center gap-2">
          <strong>{{ String(preview.pending_step.command?.name || preview.pending_step.command?.command_key || session.pending_step_key) }}</strong>
          <n-tag type="error" size="small" round>
            {{ $t(`page.resourceLibrary.risk.${String(preview.pending_step.command?.risk || "high")}` as I18n.I18nKey) }}
          </n-tag>
          <span class="aira-type-meta">v{{ String(preview.pending_step.command?.command_version || "") }} · r{{ String(preview.pending_step.command?.revision || "") }}</span>
        </div>
        <pre class="mt-3">{{ JSON.stringify(preview.pending_step.arguments || {}, null, 2) }}</pre>
      </div>
    </template>

    <template #footer>
      <div class="flex justify-end gap-2">
        <n-button @click="preview ? (preview = null) : (visible = false)">
          {{ preview ? $t("page.research.backToEdit") : $t("common.cancel") }}
        </n-button>
        <n-button
          v-if="!preview"
          :type="mode === 'resume' ? 'primary' : 'error'"
          :disabled="!reason.trim()"
          :loading="submitting"
          @click="previewDecision"
        >
          {{ $t("page.research.previewAction") }}
        </n-button>
        <n-button
          v-else
          :type="mode === 'resume' ? 'primary' : 'error'"
          :loading="submitting"
          @click="confirmDecision"
        >
          {{ mode === "resume" ? $t("page.research.confirmResumeControl") : $t("page.research.confirmStopControl") }}
        </n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import type {
  DigitalActionPreview,
  InstrumentControlDecisionDraft,
} from "@/service/api/research-actions"
import type {
  ResearchInstrumentControlSession,
  ResearchInstrumentJob,
} from "@/service/api/research-tasks"
import {
  previewInstrumentControlResume,
  previewInstrumentControlStop,
  resumeInstrumentControlSession,
  stopInstrumentControlSession,
} from "@/service/api/research-actions"
import { $t } from "@airalogy/shared/locales"

const props = defineProps<{
  session: ResearchInstrumentControlSession
  job: ResearchInstrumentJob
}>()
const emit = defineEmits<{ changed: [] }>()

const visible = ref(false)
const mode = ref<"resume" | "stop">("resume")
const reason = ref("")
const submitting = ref(false)
const preview = ref<DigitalActionPreview<InstrumentControlDecisionDraft> | null>(null)
const finalStatuses = new Set(["completed", "failed", "cancelled", "stopped"])
const isCurrent = computed(() => {
  const index = props.job.control_execution_index || 0
  return index === props.session.issued_steps
})
const canResume = computed(() =>
  props.session.status === "paused_for_review" && Boolean(props.session.pending_step_key),
)
const canStop = computed(() => !finalStatuses.has(props.session.status))

function open(nextMode: "resume" | "stop") {
  mode.value = nextMode
  visible.value = true
}

function payload(): InstrumentControlDecisionDraft {
  return {
    expected_revision: props.session.revision,
    reason: reason.value.trim(),
  }
}

async function previewDecision() {
  submitting.value = true
  try {
    preview.value = mode.value === "resume"
      ? await previewInstrumentControlResume(props.session.id, payload())
      : await previewInstrumentControlStop(props.session.id, payload())
  }
  finally {
    submitting.value = false
  }
}

async function confirmDecision() {
  if (!preview.value)
    return
  submitting.value = true
  try {
    const request = {
      ...payload(),
      preview_digest: preview.value.preview_digest,
    }
    if (mode.value === "resume")
      await resumeInstrumentControlSession(props.session.id, request)
    else
      await stopInstrumentControlSession(props.session.id, request)
    visible.value = false
    window.$message?.success(
      mode.value === "resume"
        ? $t("page.research.instrumentControlResumed")
        : $t("page.research.instrumentStopRequested"),
    )
    emit("changed")
  }
  finally {
    submitting.value = false
  }
}

function reset() {
  reason.value = ""
  preview.value = null
}
</script>

<style scoped>
.control-decision-facts {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.75rem;
}

.control-decision-facts > div,
.control-decision-preview {
  border: 1px solid rgb(226 232 240);
  border-radius: 0.75rem;
  background: rgb(248 250 252);
  padding: 0.875rem;
}

.control-decision-facts dt {
  color: rgb(100 116 139);
  font-size: 0.75rem;
}

.control-decision-facts dd {
  margin-top: 0.25rem;
  overflow-wrap: anywhere;
  font-weight: 600;
}

:global(.research-instrument-control-decision-modal) {
  width: min(38rem, calc(100vw - 2rem));
}
</style>
