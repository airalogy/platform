<template>
  <n-button
    v-if="canCancel"
    secondary
    type="error"
    size="small"
    @click="visible = true"
  >
    {{ $t("page.research.cancelCompute") }}
  </n-button>

  <n-modal
    v-model:show="visible"
    preset="card"
    class="research-compute-cancel-modal"
    :title="$t('page.research.cancelCompute')"
    :mask-closable="false"
    @after-leave="reset"
  >
    <template v-if="!preview">
      <n-alert type="warning">
        {{ $t("page.research.computeCancelHint") }}
      </n-alert>
      <n-form label-placement="top" class="mt-4">
        <n-form-item :label="$t('page.research.computeCancelReason')" required>
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
        {{ $t("page.research.computeCancelPreviewHint") }}
      </n-alert>
      <div class="compute-cancel-preview mt-4">
        <div class="aira-type-eyebrow">
          {{ $t("page.research.effects") }}
        </div>
        <ul class="mb-0 mt-2 pl-5">
          <li v-for="effect in preview.effects" :key="effect">
            {{ effect }}
          </li>
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
          @click="previewCancel"
        >
          {{ $t("page.research.previewAction") }}
        </n-button>
        <n-button v-else type="error" :loading="submitting" @click="confirmCancel">
          {{ $t("page.research.confirmComputeCancel") }}
        </n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import type { ResearchComputeJob } from "@/service/api/research-compute-jobs"
import {
  cancelComputeJob,
  previewComputeCancellation,
} from "@/service/api/research-compute-jobs"
import { $t } from "@airalogy/shared/locales"

const props = defineProps<{ job: ResearchComputeJob }>()
const emit = defineEmits<{ changed: [] }>()

const visible = ref(false)
const reason = ref("")
const submitting = ref(false)
const preview = ref<{ preview_digest: string, effects: string[] } | null>(null)
const canCancel = computed(() => [
  "awaiting_approval",
  "queued",
  "leased",
  "running",
].includes(props.job.status))

async function previewCancel() {
  submitting.value = true
  try {
    preview.value = await previewComputeCancellation(props.job, reason.value.trim())
  }
  finally {
    submitting.value = false
  }
}

async function confirmCancel() {
  if (!preview.value)
    return
  submitting.value = true
  try {
    await cancelComputeJob(props.job, reason.value.trim(), preview.value.preview_digest)
    visible.value = false
    window.$message?.success($t("page.research.computeCancelRequested"))
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
.compute-cancel-preview {
  border: 1px solid rgb(254 202 202);
  border-radius: 0.875rem;
  background: rgb(254 242 242);
  padding: 1rem;
}

:global(.research-compute-cancel-modal) {
  width: min(36rem, calc(100vw - 2rem));
}
</style>
