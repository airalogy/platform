<script setup lang="ts">
import type { DeviceBinding, InstallationDraft, InstallationPreview, PublicInstallationRequest } from "@/service/api/instrument-installations"
import type { AdapterRelease } from "@/service/api/instrument-packages"
import { confirmInstallation, confirmInstallationRevocation, fetchInstallationHistory, fetchInstallations, previewInstallation, previewInstallationRevocation } from "@/service/api/instrument-installations"
import { fetchAdapterPackages } from "@/service/api/instrument-packages"
import { $t } from "@airalogy/shared/locales"
import InstrumentActivationsPanel from "./instrument-activations-panel.vue"
import InstrumentQualificationsPanel from "./instrument-qualifications-panel.vue"

const props = defineProps<{ labId: string, gatewayId: string, equipmentOptions: Array<{ label: string, value: string }>, resourceId?: string, requireEquipment?: boolean }>()
const busy = ref(false)
const items = ref<DeviceBinding[]>([])
const releases = ref<AdapterRelease[]>([])
const moreReleases = ref(false)
const more = ref(false)
const offset = ref(0)
const showCreate = ref(false)
const publicText = ref("")
const draft = reactive({ resource_id: "", release_id: "", reason: "", fingerprint_confirmed: false })
const parsed = computed<PublicInstallationRequest | null>(() => {
  try {
    if (publicText.value.length > 16384)
      return null
    const value = JSON.parse(publicText.value)
    // Prevent accidentally sending the private credential file to the API.
    if (!value || Object.keys(value).sort().join(",") !== "credential_digest,descriptor,fingerprint,gateway_id,id,lab_id,schema" || value.schema !== "airalogy.installation-request.v1" || value.lab_id !== props.labId || value.gateway_id !== props.gatewayId)
      return null
    const descriptorKeys = "architecture,archive_digest,configuration_digest,entry_point,installation_id,interpreter_digest,local_preview_digest,manifest_digest,platform,python_version,sdk_digest"
    if (!value.descriptor || Object.keys(value.descriptor).sort().join(",") !== descriptorKeys)
      return null
    return value
  }
  catch {
    return null
  }
})
const matchingReleases = computed(() => releases.value.filter(item => item.state === "approved" && item.archive_digest === parsed.value?.descriptor.archive_digest).map(item => ({ label: `${item.package_key} · ${item.package_version}`, value: item.id })))
const preview = ref<InstallationPreview | null>(null)
const selected = ref<DeviceBinding | null>(null)
const history = ref<Awaited<ReturnType<typeof fetchInstallationHistory>>["items"]>([])
const revokeReason = ref("")
const revokeDigest = ref("")

async function guarded(action: () => Promise<void>) {
  if (busy.value)
    return
  busy.value = true
  try {
    await action()
  }
  catch { window.$message?.error($t("page.resourceLibrary.installRetry")) }
  finally { busy.value = false }
}
async function refresh(append = false) {
  const response = await fetchInstallations(props.gatewayId, append ? offset.value : 0, props.resourceId)
  items.value = append ? [...items.value, ...response.items] : response.items
  offset.value = response.next_offset
  more.value = response.has_more
}
async function loadReleases(append = false) {
  const response = await fetchAdapterPackages(props.labId, append ? releases.value.length : 0)
  releases.value = append ? [...releases.value, ...response.items] : response.items
  moreReleases.value = response.has_more
}
async function openCreate() {
  if (props.requireEquipment && !props.resourceId)
    return
  publicText.value = ""
  preview.value = null
  Object.assign(draft, { resource_id: props.resourceId || (props.equipmentOptions.length === 1 ? props.equipmentOptions[0].value : ""), release_id: "", reason: "", fingerprint_confirmed: false })
  await loadReleases()
  showCreate.value = true
}
watch(matchingReleases, (options) => {
  if (!preview.value)
    draft.release_id = options.length === 1 ? options[0].value : ""
})
async function authorize() {
  if (!parsed.value)
    return
  const input: InstallationDraft = { ...draft, request: parsed.value }
  if (!preview.value) {
    preview.value = await previewInstallation(input)
    return
  }
  await confirmInstallation({ ...input, preview_digest: preview.value.preview_digest })
  showCreate.value = false
  await refresh()
  window.$message?.success($t("page.resourceLibrary.installAuthorized"))
}
async function inspect(item: DeviceBinding) {
  selected.value = item
  revokeReason.value = ""
  revokeDigest.value = ""
  history.value = []
  history.value = (await fetchInstallationHistory(item.id)).items
}
async function revoke() {
  if (!selected.value)
    return
  const item = selected.value
  if (!revokeDigest.value) {
    revokeDigest.value = (await previewInstallationRevocation(item.id, item.revision, revokeReason.value)).preview_digest
    return
  }
  await confirmInstallationRevocation(item.id, item.revision, revokeReason.value, revokeDigest.value)
  selected.value = null
  await refresh()
}
onMounted(() => guarded(() => refresh()))
</script>

<template>
  <section class="my-6 min-w-0" data-testid="instrument-installations-panel">
    <h3>{{ $t("page.resourceLibrary.installTitle") }}</h3>
    <p class="my-3">
      {{ $t("page.resourceLibrary.installHint") }}
    </p>
    <n-space class="mb-3">
      <n-button :disabled="busy || (requireEquipment && !resourceId)" @click="guarded(openCreate)">
        {{ $t("page.resourceLibrary.installAuthorize") }}
      </n-button>
      <n-button :loading="busy" @click="guarded(() => refresh())">
        {{ $t("common.refresh") }}
      </n-button>
    </n-space>
    <n-empty v-if="!busy && !items.length" :description="$t('page.resourceLibrary.installEmpty')" />
    <article v-for="item in items" :key="item.id" class="mb-3 min-w-0 border border-gray-200 rounded-lg p-3">
      <div class="flex flex-wrap items-center gap-2">
        <strong class="break-all">{{ equipmentOptions.find(option => option.value === item.resource_id)?.label || item.resource_id }}</strong>
        <n-tag>{{ $t(`page.resourceLibrary.installState.${item.state}`) }}</n-tag>
        <n-button size="small" :disabled="busy" @click="guarded(() => inspect(item))">
          {{ $t("page.resourceLibrary.adapterInspect") }}
        </n-button>
      </div>
      <code class="my-2 block break-all text-xs">{{ item.descriptor.entry_point }} · SHA-256: {{ item.descriptor.archive_digest }}</code>
      <p>{{ $t("page.resourceLibrary.installNotQualified") }}</p>
      <p v-if="item.state === 'authorized' || item.state === 'installing'">
        {{ $t("page.resourceLibrary.pairingExpiry") }} {{ new Date(item.expires_at).toLocaleString() }}
      </p>
    </article>
    <n-button v-if="more" :loading="busy" @click="guarded(() => refresh(true))">
      {{ $t("page.resourceLibrary.installMore") }}
    </n-button>
    <n-modal v-model:show="showCreate" preset="card" class="aira-dialog" :title="$t('page.resourceLibrary.installAuthorize')" :mask-closable="false" style="--aira-dialog-width: 48rem">
      <n-alert type="warning" class="mb-3">
        {{ $t("page.resourceLibrary.installRequestHint") }}
      </n-alert>
      <n-form label-placement="top">
        <n-form-item :label="$t('page.resourceLibrary.installPublicRequest')" required>
          <n-input v-model:value="publicText" type="textarea" :rows="5" :maxlength="16384" :disabled="!!preview || busy" data-testid="installation-request" />
        </n-form-item>
        <p v-if="publicText && !parsed" role="alert" class="mb-3">
          {{ $t("page.resourceLibrary.installInvalidRequest") }}
        </p>
        <code v-if="parsed" class="mb-3 block break-all text-xs">{{ $t("page.resourceLibrary.installFingerprint") }}: {{ parsed.fingerprint }}</code>
        <n-form-item :label="$t('page.resourceLibrary.equipment')" required>
          <n-select v-model:value="draft.resource_id" :options="equipmentOptions" :disabled="!!preview || busy" data-testid="installation-equipment" />
        </n-form-item>
        <n-form-item :label="$t('page.resourceLibrary.installRelease')" required>
          <n-select v-model:value="draft.release_id" :options="matchingReleases" :disabled="!!preview || busy" />
        </n-form-item>
        <n-button v-if="moreReleases && !preview" class="mb-3" :loading="busy" @click="guarded(() => loadReleases(true))">
          {{ $t("page.resourceLibrary.adapterMore") }}
        </n-button>
        <n-form-item :label="$t('page.resourceLibrary.changeReason')" required>
          <n-input v-model:value="draft.reason" type="textarea" :maxlength="2000" :disabled="!!preview || busy" data-testid="installation-reason" />
        </n-form-item>
        <n-checkbox v-model:checked="draft.fingerprint_confirmed" :disabled="!!preview || busy">
          {{ $t("page.resourceLibrary.installFingerprintConfirm") }}
        </n-checkbox>
      </n-form>
      <template v-if="preview">
        <n-alert type="warning" class="my-3">
          {{ $t("page.resourceLibrary.installImpact") }}
        </n-alert>
        <pre class="max-h-64 overflow-auto whitespace-pre-wrap break-all text-xs">{{ JSON.stringify({ lab: labId, gateway: gatewayId, equipment: draft.resource_id, equipment_revision: preview.resource_revision, release: draft.release_id, release_revision: preview.release_revision, descriptor: parsed?.descriptor }, null, 2) }}</pre>
      </template>
      <template #footer>
        <n-space justify="end">
          <n-button :disabled="busy" @click="showCreate = false">
            {{ $t("common.cancel") }}
          </n-button>
          <n-button v-if="preview" :disabled="busy" @click="preview = null">
            {{ $t("common.previous") }}
          </n-button>
          <n-button type="primary" :loading="busy" :disabled="!parsed || !draft.resource_id || !draft.release_id || !draft.reason.trim() || !draft.fingerprint_confirmed" @click="guarded(authorize)">
            {{ preview ? $t("common.confirm") : $t("common.preview") }}
          </n-button>
        </n-space>
      </template>
    </n-modal>
    <n-modal :show="!!selected" preset="card" class="aira-dialog" :title="$t('page.resourceLibrary.installTitle')" :mask-closable="false" style="--aira-dialog-width: 48rem" @update:show="selected = null">
      <template v-if="selected">
        <n-alert type="info" class="mb-3">
          {{ $t("page.resourceLibrary.installNotQualified") }}
        </n-alert>
        <pre class="max-h-56 overflow-auto whitespace-pre-wrap break-all text-xs">{{ JSON.stringify(selected.descriptor, null, 2) }}</pre>
        <h4 class="my-3">
          {{ $t("page.resourceLibrary.installHistory") }}
        </h4>
        <p v-for="entry in history" :key="entry.revision" class="mb-2 break-words">
          #{{ entry.revision }} · {{ $t(`page.resourceLibrary.installEvent.${entry.action}`) }} · {{ new Date(entry.created_at).toLocaleString() }}<br>{{ entry.reason }}
        </p>
        <instrument-qualifications-panel :key="selected.id" :binding-id="selected.id" :installed="selected.state === 'installed'" />
        <instrument-activations-panel :key="`active-${selected.id}`" :binding-id="selected.id" :installed="selected.state === 'installed'" />
        <template v-if="selected.state !== 'revoked'">
          <n-form-item :label="$t('page.resourceLibrary.changeReason')" required>
            <n-input v-model:value="revokeReason" :disabled="busy || !!revokeDigest" :maxlength="2000" type="textarea" />
          </n-form-item>
          <n-alert v-if="revokeDigest" type="warning">
            {{ $t("page.resourceLibrary.installRevokeImpact") }}
          </n-alert>
        </template>
      </template>
      <template #footer>
        <n-space justify="end">
          <n-button :disabled="busy" @click="selected = null">
            {{ $t("common.close") }}
          </n-button>
          <n-button v-if="revokeDigest" :disabled="busy" @click="revokeDigest = ''">
            {{ $t("common.previous") }}
          </n-button>
          <n-button v-if="selected?.state !== 'revoked'" type="warning" :loading="busy" :disabled="!revokeReason.trim()" @click="guarded(revoke)">
            {{ revokeDigest ? $t("common.confirm") : $t("page.resourceLibrary.installRevoke") }}
          </n-button>
        </n-space>
      </template>
    </n-modal>
  </section>
</template>
