<template>
  <n-button
    v-if="canStop"
    secondary
    type="error"
    size="small"
    @click="visible = true"
  >
    {{ $t("page.research.requestInstrumentStop") }}
  </n-button>

  <n-modal
    v-model:show="visible"
    preset="card"
    class="research-instrument-stop-modal"
    :title="$t('page.research.requestInstrumentStop')"
    :mask-closable="false"
    @after-leave="reset"
  >
    <template v-if="!preview">
      <n-alert type="warning">
        {{ $t("page.research.instrumentStopHint") }}
      </n-alert>
      <n-form label-placement="top" class="mt-4">
        <n-form-item :label="$t('page.research.stopReason')" required>
          <n-input
            v-model:value="reason"
            type="textarea"
            :autosize="{ minRows: 3, maxRows: 8 }"
          />
        </n-form-item>
      </n-form>
    </template>
    <template v-else>
      <n-alert type="error">
        {{ $t("page.research.instrumentStopConfirm") }}
      </n-alert>
      <div class="instrument-stop-preview mt-4">
        <div class="aira-type-eyebrow">
          {{ $t("page.research.effects") }}
        </div>
        <ul class="mb-0 mt-2 pl-5">
          <li>{{ $t("page.research.instrumentStopImpactPause") }}</li>
          <li>{{ $t("page.research.instrumentStopImpactAcknowledge") }}</li>
        </ul>
      </div>
    </template>

    <template #footer>
      <div class="flex justify-end gap-2">
        <n-button @click="preview ? (preview = null) : (visible = false)">
          {{ preview ? $t("page.research.backToEdit") : $t("common.cancel") }}
        </n-button>
        <n-button
          v-if="!preview"
          type="error"
          :disabled="!reason.trim()"
          :loading="submitting"
          @click="previewStop"
        >
          {{ $t("page.research.previewAction") }}
        </n-button>
        <n-button v-else type="error" :loading="submitting" @click="confirmStop">
          {{ $t("page.research.confirmInstrumentStop") }}
        </n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import type { DigitalActionPreview, InstrumentStopDraft } from "@/service/api/research-actions"
import type { ResearchInstrumentJob } from "@/service/api/research-tasks"
import {
  previewInstrumentStop,
  stopInstrumentJob,
} from "@/service/api/research-actions"
import { $t } from "@airalogy/shared/locales"

const props = defineProps<{ job: ResearchInstrumentJob }>()
const emit = defineEmits<{ stopped: [] }>()

const visible = ref(false)
const reason = ref("")
const submitting = ref(false)
const preview = ref<DigitalActionPreview<InstrumentStopDraft> | null>(null)
const canStop = computed(() =>
  ["queued", "leased", "running", "stop_requested"].includes(props.job.status),
)

function payload(): InstrumentStopDraft {
  return {
    expected_revision: props.job.revision,
    reason: reason.value.trim(),
  }
}

async function previewStop() {
  submitting.value = true
  try {
    preview.value = await previewInstrumentStop(props.job.id, payload())
  }
  finally {
    submitting.value = false
  }
}

async function confirmStop() {
  if (!preview.value)
    return
  submitting.value = true
  try {
    await stopInstrumentJob(props.job.id, {
      ...payload(),
      preview_digest: preview.value.preview_digest,
    })
    visible.value = false
    window.$message?.success($t("page.research.instrumentStopRequested"))
    emit("stopped")
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
.instrument-stop-preview {
  border: 1px solid rgb(254 202 202);
  border-radius: 0.875rem;
  background: rgb(254 242 242);
  padding: 1rem;
}

:global(.research-instrument-stop-modal) {
  width: min(36rem, calc(100vw - 2rem));
}
</style>
