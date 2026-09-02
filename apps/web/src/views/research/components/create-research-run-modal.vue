<template>
  <n-button secondary @click="open">
    <template #icon>
      <n-icon><icon-tabler-repeat /></n-icon>
    </template>
    {{ $t("page.research.newRun") }}
  </n-button>

  <n-modal
    v-model:show="visible"
    preset="card"
    class="research-run-modal"
    :title="$t('page.research.createRunTitle')"
    :mask-closable="false"
    @after-leave="reset"
  >
    <template v-if="!preview">
      <n-alert type="info" class="mb-4">
        {{ $t("page.research.runInheritanceHint") }}
      </n-alert>
      <n-form label-placement="top">
        <n-form-item :label="$t('page.research.sourceRun')" required>
          <n-select v-model:value="sourceRunId" :options="sourceOptions" />
        </n-form-item>
        <n-form-item :label="$t('page.research.runKind')" required>
          <n-select v-model:value="kind" :options="kindOptions" />
        </n-form-item>
        <n-form-item :label="$t('page.research.runPurpose')" required>
          <n-input
            v-model:value="purpose"
            type="textarea"
            :autosize="{ minRows: 4, maxRows: 10 }"
            :placeholder="$t('page.research.runPurposePlaceholder')"
          />
        </n-form-item>
      </n-form>
    </template>
    <template v-else>
      <n-alert type="warning">
        {{ $t("page.research.runPreviewWarning") }}
      </n-alert>
      <section class="research-run-preview mt-4">
        <div class="aira-type-eyebrow">
          {{ $t("page.research.saveDestination") }}
        </div>
        <h3 class="aira-type-card-title mb-0 mt-2">
          {{ preview.destination.lab.name }} / {{ preview.destination.project.name }}
        </h3>
        <div class="aira-type-body aira-text-secondary mt-3 space-y-2">
          <div>
            {{ $t("page.research.sourceRun") }} · #{{ preview.source_run.run_number }}
          </div>
          <div>
            {{ $t("page.research.newRun") }} · #{{ preview.new_run.run_number }} ·
            {{ runKindLabel(preview.new_run.kind) }}
          </div>
          <div class="break-all">
            {{ $t("page.research.environmentDigest") }} ·
            {{ preview.source_run.environment_digest }}
          </div>
        </div>
      </section>
      <ul class="aira-type-body aira-text-secondary mb-0 mt-4 pl-5 space-y-2">
        <li>{{ $t("page.research.runEffectCreate") }}</li>
        <li>{{ $t("page.research.runEffectInherit") }}</li>
        <li>{{ $t("page.research.runEffectPreserve") }}</li>
        <li>{{ $t("page.research.runEffectReopen") }}</li>
      </ul>
    </template>

    <template #footer>
      <div class="flex justify-end gap-2">
        <n-button @click="preview ? preview = null : visible = false">
          {{ preview ? $t("page.research.backToEdit") : $t("common.cancel") }}
        </n-button>
        <n-button
          v-if="!preview"
          type="primary"
          :disabled="!valid"
          :loading="submitting"
          @click="handlePreview"
        >
          {{ $t("page.research.previewRun") }}
        </n-button>
        <n-button v-else type="primary" :loading="submitting" @click="handleCreate">
          {{ $t("page.research.confirmRun") }}
        </n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import type {
  ResearchRun,
  ResearchRunDraft,
  ResearchRunOrigin,
  ResearchRunPreview,
} from "@/service/api/research-tasks"
import {
  createResearchRun,
  previewResearchRun,
} from "@/service/api/research-tasks"
import { $t } from "@airalogy/shared/locales"
import { nanoid } from "nanoid"

const props = defineProps<{
  taskId: string
  taskRevision: number
  runs: ResearchRun[]
}>()
const emit = defineEmits<{ created: [] }>()

const visible = ref(false)
const submitting = ref(false)
const preview = ref<ResearchRunPreview | null>(null)
const sourceRunId = ref("")
const kind = ref<ResearchRunOrigin["kind"]>("replication")
const purpose = ref("")
let previewPayload: ResearchRunDraft | null = null

const terminalRuns = computed(() => props.runs.filter(run =>
  ["completed", "failed", "cancelled"].includes(run.status),
))
const sourceOptions = computed(() => terminalRuns.value.map(run => ({
  label: `#${run.run_number} · ${runStatusLabel(run.status)}`,
  value: run.id,
})))
const kindOptions = computed(() => (["retry", "replication", "continuation"] as const).map(value => ({
  label: runKindLabel(value),
  value,
})))
const valid = computed(() => Boolean(sourceRunId.value && purpose.value.trim()))

function runKindLabel(value: ResearchRunOrigin["kind"]) {
  return $t(`page.research.runKinds.${value}` as I18n.I18nKey)
}

function runStatusLabel(value: ResearchRun["status"]) {
  return $t(`page.research.runStatus.${value}` as I18n.I18nKey)
}

function reset() {
  preview.value = null
  previewPayload = null
  sourceRunId.value = ""
  kind.value = "replication"
  purpose.value = ""
}

function open() {
  const source = terminalRuns.value[0]
  sourceRunId.value = source?.id || ""
  kind.value = source?.status === "completed" ? "replication" : "retry"
  visible.value = true
}

function payload(): ResearchRunDraft {
  return {
    expected_task_revision: props.taskRevision,
    source_run_id: sourceRunId.value,
    kind: kind.value,
    purpose: purpose.value.trim(),
    idempotency_key: `run-${nanoid()}`,
  }
}

async function handlePreview() {
  if (!valid.value)
    return
  submitting.value = true
  try {
    previewPayload = payload()
    preview.value = await previewResearchRun(props.taskId, previewPayload)
  }
  finally {
    submitting.value = false
  }
}

async function handleCreate() {
  if (!preview.value || !previewPayload)
    return
  submitting.value = true
  try {
    await createResearchRun(props.taskId, {
      ...previewPayload,
      preview_digest: preview.value.preview_digest,
    })
    window.$message?.success($t("page.research.runCreated"))
    visible.value = false
    emit("created")
  }
  finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.research-run-modal {
  width: min(40rem, calc(100vw - 2rem));
}

.research-run-preview {
  border: 1px solid rgb(226 232 240);
  border-radius: 0.75rem;
  background: rgb(248 250 252 / 75%);
  padding: 1rem;
}
</style>
