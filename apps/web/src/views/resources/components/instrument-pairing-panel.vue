<script setup lang="ts">
import type { InstrumentPairing } from "@/service/api/instrument-pairings"
import type { InstrumentGateway } from "@/service/api/research-instruments"
import { cancelPairing, confirmPairing, createPairing, fetchPairings, previewPairing, previewPairingConfirmation } from "@/service/api/instrument-pairings"
import { $t } from "@airalogy/shared/locales"

const props = defineProps<{ gateway: InstrumentGateway }>()
const emit = defineEmits<{ updated: [] }>()
const items = ref<InstrumentPairing[]>([])
const busy = ref(false)
const show = ref(false)
const reason = ref("")
const createPreview = ref("")
const code = ref("")
const issued = ref<InstrumentPairing | null>(null)
const confirmation = ref<{ pairing: InstrumentPairing, preview_digest: string } | null>(null)
const matched = ref(false)

async function guarded(action: () => Promise<void>) {
  if (busy.value)
    return
  busy.value = true
  try {
    await action()
  }
  catch {
    window.$message?.error($t("page.resourceLibrary.pairingRetry"))
  }
  finally {
    busy.value = false
  }
}
async function refresh() {
  items.value = (await fetchPairings(props.gateway.id)).items
}
function open() {
  reason.value = ""
  code.value = ""
  issued.value = null
  createPreview.value = ""
  show.value = true
}
async function preview() {
  await guarded(async () => {
    createPreview.value = (await previewPairing({ gateway_id: props.gateway.id, expected_revision: props.gateway.revision, reason: reason.value })).preview_digest
  })
}
async function issue() {
  await guarded(async () => {
    const result = await createPairing({ gateway_id: props.gateway.id, expected_revision: props.gateway.revision, reason: reason.value, preview_digest: createPreview.value })
    code.value = result.code
    issued.value = result.pairing
    await refresh()
  })
}
async function review(item: InstrumentPairing) {
  await guarded(async () => {
    matched.value = false
    confirmation.value = await previewPairingConfirmation(item.id)
  })
}
async function confirm() {
  if (!confirmation.value || !matched.value)
    return
  await guarded(async () => {
    await confirmPairing(confirmation.value!.pairing.id, confirmation.value!.preview_digest)
    confirmation.value = null
    await refresh()
    emit("updated")
    window.$message?.success($t("page.resourceLibrary.pairingDone"))
  })
}
onMounted(() => guarded(refresh))
watch(show, (visible) => {
  if (!visible) {
    code.value = ""
    issued.value = null
  }
})
</script>

<template>
  <section class="my-6" data-testid="instrument-pairing-panel">
    <h3 class="mb-2">
      {{ $t("page.resourceLibrary.pairingTitle") }}
    </h3>
    <n-alert type="info" :bordered="false" class="mb-3">
      {{ $t("page.resourceLibrary.pairingHint") }}
    </n-alert>
    <n-space class="mb-3">
      <n-button :disabled="gateway.enabled || busy" @click="open">
        {{ $t("page.resourceLibrary.pairingCreate") }}
      </n-button>
      <n-button :loading="busy" @click="guarded(refresh)">
        {{ $t("common.refresh") }}
      </n-button>
    </n-space>
    <div v-for="item in items" :key="item.id" class="mb-3 border border-gray-200 rounded-lg p-3">
      <div class="flex flex-wrap items-center gap-2">
        <strong class="break-all">{{ item.client_name || $t("page.resourceLibrary.pairingWaiting") }}</strong>
        <n-tag size="small">
          {{ $t(`page.resourceLibrary.pairingState.${item.state}`) }}
        </n-tag>
        <n-button v-if="item.state === 'claimed'" size="small" :disabled="busy" @click="review(item)">
          {{ $t("common.preview") }}
        </n-button>
        <n-button v-if="['pending', 'claimed'].includes(item.state)" size="small" :disabled="busy" @click="guarded(async () => { await cancelPairing(item.id); await refresh() })">
          {{ $t("common.cancel") }}
        </n-button>
      </div>
      <p class="mt-1 break-all text-xs text-gray-500">
        {{ item.id }}
      </p>
    </div>
    <n-modal v-model:show="show" preset="card" class="aira-dialog" :title="$t('page.resourceLibrary.pairingCreate')" :mask-closable="false" style="--aira-dialog-width: 40rem">
      <template v-if="!issued">
        <n-alert type="warning" class="mb-3">
          {{ $t("page.resourceLibrary.pairingImpact") }}
        </n-alert>
        <n-form-item :label="$t('page.resourceLibrary.changeReason')" required>
          <n-input v-model:value="reason" :disabled="!!createPreview" data-testid="pairing-reason" />
        </n-form-item>
      </template>
      <template v-else>
        <n-alert type="warning" class="mb-3">
          {{ $t("page.resourceLibrary.pairingSecretHint") }}
        </n-alert>
        <p class="mb-2 break-all">
          Lab: {{ issued.lab_id }}<br>Gateway: {{ issued.gateway_id }}
        </p>
        <n-input :value="code" readonly type="textarea" data-testid="pairing-code" />
        <p class="mt-2">
          {{ $t("page.resourceLibrary.pairingExpiry") }} {{ new Date(issued.expires_at).toLocaleString() }}
        </p>
      </template>
      <template #footer>
        <n-space justify="end">
          <n-button @click="show = false">
            {{ $t("common.close") }}
          </n-button>
          <n-button v-if="!issued && createPreview" :disabled="busy" @click="createPreview = ''">
            {{ $t("common.previous") }}
          </n-button>
          <n-button v-if="!issued" type="primary" :loading="busy" :disabled="!reason.trim()" @click="createPreview ? issue() : preview()">
            {{ createPreview ? $t("common.confirm") : $t("common.preview") }}
          </n-button>
        </n-space>
      </template>
    </n-modal>
    <n-modal :show="!!confirmation" preset="card" class="aira-dialog" :title="$t('page.resourceLibrary.pairingReview')" :mask-closable="false" style="--aira-dialog-width: 40rem" @update:show="confirmation = null">
      <template v-if="confirmation">
        <n-alert type="warning" class="mb-3">
          {{ $t("page.resourceLibrary.pairingConfirmImpact") }}
        </n-alert>
        <p class="break-all">
          {{ confirmation.pairing.client_name }}
        </p>
        <code class="my-3 block break-all" data-testid="pairing-fingerprint">{{ confirmation.pairing.fingerprint }}</code>
        <n-checkbox v-model:checked="matched">
          {{ $t("page.resourceLibrary.pairingMatch") }}
        </n-checkbox>
      </template>
      <template #footer>
        <n-space justify="end">
          <n-button @click="confirmation = null">
            {{ $t("common.cancel") }}
          </n-button>
          <n-button type="primary" :disabled="!matched" :loading="busy" @click="confirm">
            {{ $t("common.confirm") }}
          </n-button>
        </n-space>
      </template>
    </n-modal>
  </section>
</template>
