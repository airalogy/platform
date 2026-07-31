<template>
  <span aria-hidden="true" />
</template>

<script setup lang="ts">
import { fetchRecordExports, markRecordExportSeen } from "@/service/api/record-exports"
import { useAuthStore } from "@/store/modules/auth"
import { useNotification } from "naive-ui"
import { useI18n } from "vue-i18n"

defineOptions({ name: "RecordExportNotifier" })

const authStore = useAuthStore()
const notification = useNotification()
const { t } = useI18n()
let timer: ReturnType<typeof setInterval> | undefined
let checking = false

async function checkExports() {
  if (!authStore.isLogin || checking)
    return
  checking = true
  try {
    const { data } = await fetchRecordExports({ unseenOnly: true, pageSize: 20 })
    for (const item of data?.items || []) {
      if (item.status === "succeeded") {
        notification.success({
          title: t("page.recordExport.completedTitle"),
          content: t("page.recordExport.completedMessage", { count: item.record_count }),
          duration: 8000,
        })
      }
      else if (item.status === "failed") {
        notification.error({
          title: t("page.recordExport.failedTitle"),
          content: item.error || t("page.recordExport.failedMessage"),
          duration: 0,
        })
      }
      await markRecordExportSeen(item.id)
    }
  }
  catch {
    // Notification polling is best-effort and retries on the next interval.
  }
  finally {
    checking = false
  }
}

onMounted(() => {
  void checkExports()
  timer = setInterval(checkExports, 15000)
})

onBeforeUnmount(() => {
  if (timer)
    clearInterval(timer)
})

watch(() => authStore.isLogin, value => value && void checkExports())
</script>
