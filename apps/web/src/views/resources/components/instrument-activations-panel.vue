<script setup lang="ts">
import type { ActivationDraft, ActivationRecord } from "@/service/api/instrument-activations"
import type { QualificationRecord } from "@/service/api/instrument-qualifications"
import { confirmActivation, confirmActivationRevocation, fetchActivations, previewActivation, previewActivationRevocation } from "@/service/api/instrument-activations"
import { fetchQualifications } from "@/service/api/instrument-qualifications"
import { $t } from "@airalogy/shared/locales"

const props = defineProps<{ bindingId: string, installed: boolean }>()
const busy = ref(false)
const error = ref(false)
const rows = ref<ActivationRecord[]>([])
const currentId = ref<string | null>(null)
const offset = ref(0)
const more = ref(false)
const open = ref(false)
const qualifications = ref<QualificationRecord[]>([])
const qualificationOffset = ref(0)
const moreQualifications = ref(false)
const qualificationId = ref("")
const commands = ref<string[]>([])
const expiresAt = ref<number | null>(null)
const reason = ref("")
const consent = ref(false)
const preview = ref<Awaited<ReturnType<typeof previewActivation>> | null>(null)
const prepared = ref<ActivationDraft | null>(null)
const revoking = ref<ActivationRecord | null>(null)
const revokeReason = ref("")
const revokeDigest = ref("")
const eligible = computed(() => qualifications.value.filter(row => row.effective_state === "qualified" && row.report))
const selected = computed(() => eligible.value.find(row => row.id === qualificationId.value))
const options = computed(() => (selected.value?.report?.commands || []).map(command => ({ label: `${command.key}@${command.version}`, value: `${command.key}@${command.version}` })))
const complete = computed(() => selected.value && commands.value.length && expiresAt.value && expiresAt.value > Date.now() && expiresAt.value <= Date.parse(selected.value.expires_at) && consent.value && reason.value.trim())
watch(qualificationId, () => {
  if (preview.value)
    return
  commands.value = options.value.length === 1 ? [options.value[0].value] : []
  expiresAt.value = selected.value ? Math.min(Date.parse(selected.value.expires_at), Date.now() + 86400000) : null
})
async function guarded(action: () => Promise<void>) {
  if (busy.value)
    return
  busy.value = true
  error.value = false
  try {
    await action()
  }
  catch { error.value = true }
  finally { busy.value = false }
}
async function refresh(append = false) {
  const result = await fetchActivations(props.bindingId, append ? offset.value : 0)
  rows.value = append ? [...rows.value, ...result.items] : result.items
  currentId.value = result.current_id
  offset.value = result.next_offset
  more.value = result.has_more
}
async function loadQualifications(append = false) {
  const result = await fetchQualifications(props.bindingId, append ? qualificationOffset.value : 0)
  qualifications.value = append ? [...qualifications.value, ...result.items] : result.items
  qualificationOffset.value = result.next_offset
  moreQualifications.value = result.has_more
  if (!qualificationId.value && eligible.value.length === 1)
    qualificationId.value = eligible.value[0].id
}
async function create() {
  preview.value = null
  prepared.value = null
  qualificationId.value = ""
  commands.value = []
  reason.value = ""
  consent.value = false
  await refresh()
  await loadQualifications()
  open.value = true
}
async function save() {
  if (!preview.value) {
    prepared.value = { id: crypto.randomUUID(), qualification_id: qualificationId.value, expected_active_id: currentId.value, commands: [...commands.value], expires_at: new Date(expiresAt.value!).toISOString(), reason: reason.value, activation_confirmed: consent.value }
    preview.value = await previewActivation(props.bindingId, prepared.value)
    return
  }
  await confirmActivation(props.bindingId, prepared.value!, preview.value.preview_digest)
  open.value = false
  await refresh()
  window.$message?.success($t("page.resourceLibrary.activation.saved"))
}
async function revoke() {
  const row = revoking.value!
  if (!revokeDigest.value) {
    revokeDigest.value = (await previewActivationRevocation(row.binding_id, row.id, revokeReason.value)).preview_digest
    return
  }
  await confirmActivationRevocation(row.binding_id, row.id, revokeReason.value, revokeDigest.value)
  revoking.value = null
  await refresh()
}
onMounted(() => guarded(() => refresh()))
</script>

<template>
  <section class="my-5 min-w-0" data-testid="instrument-activations">
    <h3>{{ $t("page.resourceLibrary.activation.title") }}</h3>
    <p class="my-3">
      {{ $t("page.resourceLibrary.activation.hint") }}
    </p>
    <n-alert v-if="error" type="error" class="my-3">
      {{ $t("page.resourceLibrary.qualification.retry") }}
    </n-alert>
    <n-space class="mb-3">
      <n-button :disabled="busy || !installed" @click="guarded(create)">
        {{ $t("page.resourceLibrary.activation.create") }}
      </n-button>
      <n-button :loading="busy" @click="guarded(() => refresh())">
        {{ $t("common.refresh") }}
      </n-button>
    </n-space>
    <p v-if="!rows.length">
      {{ $t("page.resourceLibrary.activation.empty") }}
    </p>
    <article v-for="row in rows" :key="row.id" class="my-3 min-w-0 border border-gray-200 rounded p-3">
      <strong>{{ $t(`page.resourceLibrary.activation.state.${row.effective_state}`) }}</strong>
      <code class="my-2 block break-all">{{ row.id }}</code>
      <template v-if="row.plan">
        <p class="my-2 break-words">
          {{ row.plan.reason }}
        </p>
        <p class="my-2">
          {{ $t("page.resourceLibrary.qualification.expiresAt") }}: {{ new Date(row.plan.expires_at).toLocaleString() }}
        </p>
        <code class="my-2 block break-all">SHA-256: {{ row.plan.descriptor.archive_digest }}</code>
        <p v-for="command in row.commands" :key="command.key" class="my-2 break-all">
          {{ command.key }}@{{ command.version }} · #{{ command.revision }}
        </p>
        <details v-if="row.id === currentId && row.effective_state === 'authorized'" class="my-3">
          <summary>{{ $t("page.resourceLibrary.activation.localStart") }}</summary>
          <p class="my-3">
            {{ $t("page.resourceLibrary.activation.localHint") }}
          </p>
          <pre class="whitespace-pre-wrap break-all text-xs">airalogy-instrument-activation preview --request /LOCAL/private-installation.json --credentials /LOCAL/gateway.json --activation {{ row.id }}
airalogy-instrument-activation run --request /LOCAL/private-installation.json --credentials /LOCAL/gateway.json --activation {{ row.id }} --confirm-digest PREVIEW_DIGEST --startup-authorized</pre>
        </details>
      </template>
      <p v-if="row.details_redacted" class="my-2">
        {{ $t("page.resourceLibrary.qualification.redacted") }}
      </p>
      <n-button v-if="row.id === currentId" :disabled="busy" @click="revoking = row; revokeReason = ''; revokeDigest = ''">
        {{ $t("page.resourceLibrary.activation.revoke") }}
      </n-button>
    </article>
    <n-button v-if="more" :loading="busy" @click="guarded(() => refresh(true))">
      {{ $t("page.resourceLibrary.installMore") }}
    </n-button>
    <n-modal v-model:show="open" preset="card" class="aira-dialog" style="--aira-dialog-width: 48rem" :title="$t('page.resourceLibrary.activation.create')" :mask-closable="false">
      <n-alert type="warning" class="mb-3">
        {{ $t("page.resourceLibrary.activation.impact") }}
      </n-alert>
      <n-alert v-if="error" type="error" class="mb-3">
        {{ $t("page.resourceLibrary.qualification.retry") }}
      </n-alert>
      <p v-if="!eligible.length" class="my-3">
        {{ $t("page.resourceLibrary.activation.noQualification") }}
      </p>
      <n-form label-placement="top" :disabled="busy || !!preview">
        <n-form-item :label="$t('page.resourceLibrary.qualification.title')" required>
          <n-select v-model:value="qualificationId" :options="eligible.map(row => ({ value: row.id, label: `${$t(`page.resourceLibrary.qualification.scope.${row.scope}`)} · ${row.id}` }))" data-testid="activation-qualification" />
        </n-form-item>
        <n-button v-if="moreQualifications && !preview" class="mb-3" :disabled="busy" @click="guarded(() => loadQualifications(true))">
          {{ $t("page.resourceLibrary.activation.moreQualifications") }}
        </n-button>
        <n-form-item :label="$t('page.resourceLibrary.qualification.commands')" required>
          <n-select v-model:value="commands" multiple :options="options" />
        </n-form-item>
        <n-form-item :label="$t('page.resourceLibrary.qualification.expiresAt')" required>
          <n-date-picker v-model:value="expiresAt" type="datetime" />
        </n-form-item>
        <n-form-item :label="$t('page.resourceLibrary.changeReason')" required>
          <n-input v-model:value="reason" type="textarea" :maxlength="2000" data-testid="activation-reason" />
        </n-form-item>
        <n-checkbox v-model:checked="consent">
          {{ $t("page.resourceLibrary.activation.consent") }}
        </n-checkbox>
      </n-form>
      <pre v-if="preview" class="my-3 max-h-72 overflow-auto whitespace-pre-wrap break-all text-xs">{{ JSON.stringify(preview, null, 2) }}</pre>
      <template #footer>
        <n-space justify="end">
          <n-button :disabled="busy" @click="open = false">
            {{ $t("common.cancel") }}
          </n-button>
          <n-button v-if="preview" :disabled="busy" @click="preview = null">
            {{ $t("common.previous") }}
          </n-button>
          <n-button type="primary" :loading="busy" :disabled="!preview && !complete" @click="guarded(save)">
            {{ preview ? $t("common.confirm") : $t("common.preview") }}
          </n-button>
        </n-space>
      </template>
    </n-modal>
    <n-modal :show="!!revoking" preset="card" class="aira-dialog" :title="$t('page.resourceLibrary.activation.revoke')" :mask-closable="false" @update:show="revoking = null">
      <n-alert type="warning" class="mb-3">
        {{ $t("page.resourceLibrary.activation.revokeImpact") }}
      </n-alert>
      <n-alert v-if="error" type="error" class="mb-3">
        {{ $t("page.resourceLibrary.qualification.retry") }}
      </n-alert>
      <n-form-item :label="$t('page.resourceLibrary.changeReason')" required>
        <n-input v-model:value="revokeReason" type="textarea" :maxlength="2000" :disabled="busy || !!revokeDigest" />
      </n-form-item>
      <template #footer>
        <n-space justify="end">
          <n-button :disabled="busy" @click="revoking = null">
            {{ $t("common.cancel") }}
          </n-button>
          <n-button v-if="revokeDigest" :disabled="busy" @click="revokeDigest = ''">
            {{ $t("common.previous") }}
          </n-button>
          <n-button type="warning" :disabled="!revokeReason.trim()" :loading="busy" @click="guarded(revoke)">
            {{ revokeDigest ? $t("common.confirm") : $t("common.preview") }}
          </n-button>
        </n-space>
      </template>
    </n-modal>
  </section>
</template>
