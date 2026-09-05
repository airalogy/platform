<template>
  <div class="flex flex-wrap gap-2">
    <n-button
      v-if="reservation.kind === 'equipment' && reservation.status === 'pending_approval'"
      size="small"
      :loading="loading"
      @click="sync"
    >
      {{ $t("page.research.syncBooking") }}
    </n-button>
    <n-button
      v-if="releasable"
      size="small"
      type="error"
      tertiary
      :loading="loading"
      @click="releaseVisible = true"
    >
      {{ $t("page.research.releaseReservation") }}
    </n-button>
  </div>

  <n-modal
    style="--aira-dialog-width: 34rem"
    v-model:show="releaseVisible"
    preset="card"
    class="aira-dialog research-release-modal"
    :title="$t('page.research.releaseReservation')"
    :mask-closable="false"
    @after-leave="reset"
  >
    <template v-if="!preview">
      <n-alert type="warning" class="mb-4">
        {{ $t("page.research.releaseReservationHint") }}
      </n-alert>
      <n-form label-placement="top">
        <n-form-item :label="$t('page.research.releaseReason')" required>
          <n-input
            v-model:value="reason"
            type="textarea"
            :autosize="{ minRows: 3, maxRows: 8 }"
          />
        </n-form-item>
      </n-form>
    </template>
    <template v-else>
      <n-alert type="warning">
        {{ preview.effect }}
      </n-alert>
      <div class="aira-type-meta mt-3">
        {{ preview.resource.name }} · r{{ reservation.revision }}
      </div>
    </template>
    <template #footer>
      <div class="flex justify-end gap-2">
        <n-button @click="preview ? preview = null : releaseVisible = false">
          {{ preview ? $t("page.research.backToEdit") : $t("common.cancel") }}
        </n-button>
        <n-button
          v-if="!preview"
          type="primary"
          :disabled="!reason.trim()"
          :loading="loading"
          @click="previewRelease"
        >
          {{ $t("page.research.previewRelease") }}
        </n-button>
        <n-button v-else type="error" :loading="loading" @click="confirmRelease">
          {{ $t("page.research.confirmRelease") }}
        </n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import type { ResearchResourceReleasePreview } from "@/service/api/research-resources"
import type { ResearchResourceReservation } from "@/service/api/research-tasks"
import {
  previewResearchResourceRelease,
  releaseResearchResourceReservation,
  syncResearchResourceReservation,
} from "@/service/api/research-resources"
import { $t } from "@airalogy/shared/locales"

const props = defineProps<{ reservation: ResearchResourceReservation }>()
const emit = defineEmits<{ changed: [] }>()

const loading = ref(false)
const releaseVisible = ref(false)
const reason = ref("")
const preview = ref<ResearchResourceReleasePreview | null>(null)
const releasable = computed(() => (
  props.reservation.kind === "inventory"
    ? props.reservation.status === "active"
    : ["pending_approval", "approved"].includes(props.reservation.status)
))

async function sync() {
  loading.value = true
  try {
    await syncResearchResourceReservation(props.reservation.id)
    emit("changed")
  }
  finally {
    loading.value = false
  }
}

async function previewRelease() {
  if (!reason.value.trim())
    return
  loading.value = true
  try {
    preview.value = await previewResearchResourceRelease(props.reservation.id, {
      expected_revision: props.reservation.revision,
      reason: reason.value.trim(),
    })
  }
  finally {
    loading.value = false
  }
}

async function confirmRelease() {
  if (!preview.value)
    return
  loading.value = true
  try {
    await releaseResearchResourceReservation(props.reservation.id, {
      expected_revision: props.reservation.revision,
      reason: reason.value.trim(),
      preview_digest: preview.value.preview_digest,
    })
    window.$message?.success($t("page.research.reservationReleased"))
    releaseVisible.value = false
    emit("changed")
  }
  finally {
    loading.value = false
  }
}

function reset() {
  reason.value = ""
  preview.value = null
}
</script>

<style scoped>

</style>
