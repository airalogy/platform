<script setup lang="ts">
import type { ExternalPolicy } from "@/service/api/external-access"
import { getExternalPolicy, saveExternalPolicy } from "@/service/api/external-access"
import { useClosableMessage } from "@airalogy/composables"
import { $t } from "@airalogy/shared/locales"

const props = defineProps<{ labId: string }>()
const policy = ref<ExternalPolicy | null>(null)
const blockedFields = ref("")
const busy = ref(false)
const failed = ref(false)
const message = useClosableMessage()
async function load() {
  busy.value = true
  failed.value = false
  policy.value = null
  const labId = props.labId
  try {
    const result = await getExternalPolicy(labId)
    if (props.labId !== labId)
      return
    policy.value = result
    blockedFields.value = result.blocked_fields.join("\n")
  }
  catch { failed.value = true }
  finally { busy.value = false }
}
async function save() {
  if (!policy.value)
    return
  busy.value = true
  try {
    policy.value = await saveExternalPolicy(props.labId, { ...policy.value, blocked_fields: blockedFields.value.split(/\r?\n/u).map(v => v.trim()).filter(Boolean) })
    message.success($t("externalAccess.saved"))
  }
  catch { message.error($t("externalAccess.failed")) }
  finally { busy.value = false }
}
watch(() => props.labId, load, { immediate: true })
</script>

<template>
  <n-card data-testid="external-policy" :title="$t('externalAccess.policyTitle')" class="my-4">
    <n-alert type="warning" class="mb-4">
      {{ $t("externalAccess.policyDescription") }}
    </n-alert>
    <n-alert v-if="failed" type="error">
      {{ $t("externalAccess.failed") }} <n-button text @click="load">
        {{ $t("externalAccess.refresh") }}
      </n-button>
    </n-alert>
    <n-form v-if="policy" label-placement="top">
      <n-form-item :label="$t('externalAccess.allowExternal')">
        <n-switch v-model:value="policy.enabled" :disabled="busy" />
      </n-form-item>
      <n-form-item :label="$t('externalAccess.blockedFields')">
        <n-input v-model:value="blockedFields" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :placeholder="$t('externalAccess.blockedFieldsHint')" />
      </n-form-item>
      <p class="mb-3 text-sm color-text-secondary">
        {{ $t("externalAccess.restrictions") }}
      </p>
      <n-button type="primary" :loading="busy" :disabled="busy" @click="save">
        {{ $t("externalAccess.savePolicy") }}
      </n-button>
    </n-form>
  </n-card>
</template>
