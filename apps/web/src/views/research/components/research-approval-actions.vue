<template>
  <div v-if="canDecide" class="flex flex-wrap gap-2">
    <n-button
      secondary
      type="error"
      :disabled="approval.status !== 'pending'"
      @click.stop="openReject"
    >
      {{ $t("page.research.rejectAction") }}
    </n-button>
    <n-button
      type="primary"
      :disabled="approval.status !== 'pending'"
      :loading="submitting"
      @click.stop="confirmApprove"
    >
      {{ $t("page.research.approveAction") }}
    </n-button>
  </div>
  <span v-else class="aira-type-meta">
    {{ $t("page.research.awaitingApprover", { name: approval.approver?.name || approval.approver?.username }) }}
  </span>

  <n-modal
    v-model:show="rejectVisible"
    preset="card"
    class="research-approval-modal"
    :title="$t('page.research.rejectAction')"
    :mask-closable="false"
  >
    <n-alert type="warning" class="mb-4">
      {{ $t("page.research.rejectHint") }}
    </n-alert>
    <n-form label-placement="top">
      <n-form-item :label="$t('page.research.decisionReason')" required>
        <n-input
          v-model:value="rejectionReason"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 8 }"
          :placeholder="$t('page.research.rejectionPlaceholder')"
        />
      </n-form-item>
    </n-form>
    <template #footer>
      <div class="flex justify-end gap-2">
        <n-button @click="rejectVisible = false">{{ $t("common.cancel") }}</n-button>
        <n-button
          type="error"
          :disabled="!rejectionReason.trim()"
          :loading="submitting"
          @click="submitRejection"
        >
          {{ $t("page.research.confirmReject") }}
        </n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import type { ResearchApproval } from "@/service/api/research-tasks"
import { approveResearchAction, rejectResearchAction } from "@/service/api/research-tasks"
import { useAuthStore } from "@/store/modules/auth"
import { $t } from "@airalogy/shared/locales"
import { useDialog } from "naive-ui"

const props = defineProps<{ approval: ResearchApproval, actionRevision: number }>()
const emit = defineEmits<{ decided: [] }>()

const authStore = useAuthStore()
const dialog = useDialog()
const submitting = ref(false)
const rejectVisible = ref(false)
const rejectionReason = ref("")
const canDecide = computed(() =>
  String(props.approval.approver_user_id) === String(authStore.userInfo.id),
)

function decisionPayload(reason: string) {
  return {
    expected_revision: props.approval.revision,
    expected_action_revision: props.actionRevision,
    preview_digest: props.approval.preview_digest,
    reason,
  }
}

function confirmApprove() {
  dialog.warning({
    title: $t("page.research.approveAction"),
    content: $t("page.research.approveHint"),
    positiveText: $t("page.research.confirmApprove"),
    negativeText: $t("common.cancel"),
    onPositiveClick: submitApproval,
  })
}

async function submitApproval() {
  submitting.value = true
  try {
    await approveResearchAction(
      props.approval.id,
      decisionPayload($t("page.research.approvedFromWorkbench")),
    )
    window.$message?.success($t("page.research.actionApproved"))
    emit("decided")
  }
  finally {
    submitting.value = false
  }
}

function openReject() {
  rejectionReason.value = ""
  rejectVisible.value = true
}

async function submitRejection() {
  const reason = rejectionReason.value.trim()
  if (!reason)
    return
  submitting.value = true
  try {
    await rejectResearchAction(props.approval.id, decisionPayload(reason))
    rejectVisible.value = false
    window.$message?.success($t("page.research.actionRejected"))
    emit("decided")
  }
  finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.research-approval-modal {
  width: min(36rem, calc(100vw - 2rem));
}
</style>
