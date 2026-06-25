<template>
  <div class="min-h-[200px] p-4">
    <template v-if="records.length">
      <div class="space-y-4">
        <n-collapse>
          <n-collapse-item
            v-for="record in records"
            :key="record.record_id"
            :title="`#${record.record_id} - ${formatDate(record.metadata.record_current_version_submission_time)}`"
          >
            <div class="space-y-2">
              <div class="flex items-center gap-2">
                <span class="text-gray-500">{{ $t("common.createdBy") }}:</span>
                <span>{{ record.metadata.record_current_version_submission_user_id }}</span>
              </div>
              <div v-if="record.data" class="mt-4">
                <div class="mb-1 text-gray-500">
                  {{ $t("common.report") }}:
                </div>
                <div class="whitespace-pre-wrap">
                  {{ record.data }}
                </div>
              </div>
            </div>
          </n-collapse-item>
        </n-collapse>
      </div>
    </template>
    <n-empty v-else :description="$t('page.hub.recordsEmpty')" />
  </div>
</template>

<script setup lang="ts">
import type { ProtocolModels } from "@airalogy/shared/types"
import { $t } from "@airalogy/shared/locales"
import { formatDate } from "@airalogy/shared/utils"

const records = ref<ProtocolModels.RecordInfo[]>([])

function getStatusType(status: string) {
  switch (status) {
    case "completed":
      return "success"
    case "in_progress":
      return "warning"
    case "failed":
      return "error"
    default:
      return "default"
  }
}

// Add your records loading logic here
</script>
