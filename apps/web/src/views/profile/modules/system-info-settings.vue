<template>
  <n-card>
    <template #header>
      <div>
        <div class="text-2xl font-semibold">
          {{ $t("page.about.systemInfo.title") }}
        </div>
        <div class="mt-1 text-sm text-gray-500">
          {{ $t("page.about.systemInfo.description") }}
        </div>
      </div>
    </template>

    <n-spin :show="loading">
      <n-alert v-if="error" type="warning" :show-icon="true">
        {{ $t("page.about.systemInfo.unavailable") }}
      </n-alert>
      <n-descriptions v-else-if="systemInfo" :column="1" label-placement="left" bordered>
        <n-descriptions-item :label="$t('page.about.systemInfo.productVersion')">
          <div class="flex flex-wrap items-center gap-2">
            <n-tag type="success" size="small">
              v{{ systemInfo.version }}
            </n-tag>
            <span v-if="systemInfo.tag" class="text-gray-500">{{ systemInfo.tag }}</span>
            <n-tag v-if="systemInfo.dirty" type="warning" size="small">
              {{ $t("page.about.systemInfo.dirtyBuild") }}
            </n-tag>
          </div>
        </n-descriptions-item>
        <n-descriptions-item :label="$t('page.about.systemInfo.sourceRevision')">
          <code>{{ systemInfo.commit }}</code>
        </n-descriptions-item>
        <n-descriptions-item :label="$t('page.about.systemInfo.databaseRevision')">
          <code>{{ systemInfo.database_revision }}</code>
        </n-descriptions-item>
        <n-descriptions-item :label="$t('page.about.systemInfo.deploymentId')">
          <code>{{ systemInfo.deployment_id || $t("common.none") }}</code>
        </n-descriptions-item>
        <n-descriptions-item :label="$t('page.about.systemInfo.releaseManifest')">
          <code class="break-all">{{
            systemInfo.release_manifest_sha256 || $t("common.none")
          }}</code>
        </n-descriptions-item>
        <n-descriptions-item :label="$t('page.about.systemInfo.buildTime')">
          {{ systemInfo.build_time || $t("common.unknown") }}
        </n-descriptions-item>
      </n-descriptions>
    </n-spin>

    <template #footer>
      <div class="flex justify-end">
        <n-button :disabled="!systemInfo" @click="copyDiagnostics">
          {{ $t("page.about.systemInfo.copyDiagnostics") }}
        </n-button>
      </div>
    </template>
  </n-card>
</template>

<script setup lang="ts">
import { $t } from "@/locales"
import { fetchSystemVersion, type SystemVersion } from "@/service/api/instance"
import { useClosableMessage } from "@airalogy/composables"
import { copyToClip } from "@airalogy/shared/utils"

defineOptions({ name: "SystemInfoSettings" })

const loading = ref(true)
const error = ref(false)
const systemInfo = ref<SystemVersion | null>(null)
const message = useClosableMessage()

async function copyDiagnostics() {
  if (!systemInfo.value)
    return
  await copyToClip(JSON.stringify(systemInfo.value, null, 2))
  message.success($t("page.about.systemInfo.copied"))
}

onMounted(async () => {
  const result = await fetchSystemVersion()
  if (result.data) {
    systemInfo.value = result.data
  }
  else {
    error.value = true
  }
  loading.value = false
})
</script>
