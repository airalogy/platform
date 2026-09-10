<script setup lang="ts">
import type { AuthoringRequest, AuthoringSession, AuthoringSourceReview, AuthoringSummary } from "@/service/api/instrument-authoring"
import { cancelAuthoring, confirmAuthoring, fetchAuthoringSession, fetchAuthoringSessions, previewAuthoring } from "@/service/api/instrument-authoring"
import { useAppStore } from "@/store/modules/app"
import { useInstanceStore } from "@/store/modules/instance"
import { $t } from "@airalogy/shared/locales"
import { documentationPageUrl } from "@airalogy/shared/utils"
import InstrumentSourceReview from "./instrument-source-review.vue"

const props = defineProps<{ gatewayId: string, equipmentOptions: Array<{ label: string, value: string }> }>()
const instance = useInstanceStore()
const appStore = useAppStore()
const guide = computed(() => documentationPageUrl(instance.documentationUrl, appStore.locale, `architecture/instrument-source-authoring#${appStore.locale === "zh-CN" ? "本地浏览器开发向导" : "local-browser-development-guide"}`))
const resourceId = ref(props.equipmentOptions.length === 1 ? props.equipmentOptions[0].value : "")
const items = ref<AuthoringSummary[]>([])
const more = ref(false)
const offset = ref(0)
const busy = ref(false)
const createVisible = ref(false)
const text = ref("")
const reason = ref("")
const consent = ref(false)
const controlledConsent = ref(false)
const serverReview = ref<AuthoringSourceReview | null>(null)
const fingerprintConfirmed = ref(false)
const previewDigest = ref("")
const fileInput = ref<HTMLInputElement>()
const selected = ref<AuthoringSession | null>(null)
const cancelReason = ref("")
const cancelConfirmed = ref(false)
const parsed = computed<AuthoringRequest | null>(() => {
  try {
    if (new TextEncoder().encode(text.value).length > 196608)
      return null
    const value = JSON.parse(text.value)
    // Never send request.json (which contains the bearer token) to Platform.
    if (!value || Object.keys(value).sort().join(",") !== "credential_digest,duration_seconds,fingerprint,gateway_id,id,max_iterations,resource_id,sandbox,schema,spec" || value.schema !== "airalogy.authoring-request.v1" || value.gateway_id !== props.gatewayId || !props.equipmentOptions.some(item => item.value === value.resource_id))
      return null
    if (!value.spec?.goal || !Array.isArray(value.spec.materials) || !value.sandbox || /(?:aiauthor_|aiinstall_|aigw_)[\w-]{43}/.test(text.value))
      return null
    const commands = value.spec.manifest?.commands
    if (!Array.isArray(commands) || !commands.length || commands.some(command => !command || !["read_only", "low", "medium", "high"].includes(command.risk) || typeof command.key !== "string" || typeof command.version !== "string" || typeof command.name !== "string" || !Array.isArray(command.effects) || command.effects.some((effect: unknown) => typeof effect !== "string") || typeof command.completion !== "string" || typeof command.stop !== "string" || !command.safety_contract))
      return null
    return value
  }
  catch { return null }
})
const needsControlledConsent = computed(() => parsed.value?.spec.manifest.commands.some(command => command.risk !== "read_only") ?? false)
watch(text, () => {
  consent.value = false
  controlledConsent.value = false
  fingerprintConfirmed.value = false
})
watch([text, reason, consent, controlledConsent, fingerprintConfirmed], () => {
  previewDigest.value = ""
  serverReview.value = null
})

async function guarded(action: () => Promise<void>) {
  if (busy.value)
    return
  busy.value = true
  try {
    await action()
  }
  catch { window.$message?.error($t("common.inputPreserved")) }
  finally { busy.value = false }
}
async function refresh(append = false) {
  if (!resourceId.value) {
    items.value = []
    more.value = false
    return
  }
  const response = await fetchAuthoringSessions(props.gatewayId, resourceId.value, append ? offset.value : 0)
  items.value = append ? [...items.value, ...response.items] : response.items
  more.value = response.has_more
  offset.value = response.next_offset
}
watch(resourceId, () => guarded(() => refresh()))
onMounted(() => guarded(() => refresh()))
function openCreate() {
  text.value = ""
  reason.value = ""
  consent.value = false
  controlledConsent.value = false
  fingerprintConfirmed.value = false
  previewDigest.value = ""
  createVisible.value = true
}
async function importFile(event: Event) {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  target.value = ""
  if (!file)
    return
  if (file.size > 196608) {
    window.$message?.error($t("page.instrumentAuthoring.invalid"))
    return
  }
  text.value = await file.text()
}
async function authorize() {
  if (!parsed.value || !consent.value || !fingerprintConfirmed.value || !reason.value.trim() || (needsControlledConsent.value && !controlledConsent.value))
    return
  const draft = { request: parsed.value, reason: reason.value, model_processing_consent: consent.value, ...(needsControlledConsent.value ? { controlled_source_consent: controlledConsent.value } : {}) }
  if (!previewDigest.value) {
    const result = await previewAuthoring(draft)
    previewDigest.value = result.preview_digest
    serverReview.value = result.source_review
    return
  }
  selected.value = await confirmAuthoring({ ...draft, preview_digest: previewDigest.value })
  resourceId.value = parsed.value.resource_id
  createVisible.value = false
  cancelReason.value = ""
  cancelConfirmed.value = false
  await refresh()
  window.$message?.success($t("page.instrumentAuthoring.authorized"))
}
async function inspect(id: string) {
  selected.value = await fetchAuthoringSession(id)
  cancelReason.value = ""
  cancelConfirmed.value = false
}
async function cancel() {
  if (!selected.value || !cancelReason.value.trim() || !cancelConfirmed.value)
    return
  selected.value = await cancelAuthoring(selected.value.id, selected.value.request.fingerprint, cancelReason.value)
  cancelReason.value = ""
  cancelConfirmed.value = false
  await refresh()
}
</script>

<template>
  <section class="my-6 min-w-0 border-t pt-4" data-testid="instrument-authoring-panel">
    <h3>{{ $t("page.instrumentAuthoring.title") }}</h3>
    <p class="my-3">
      {{ $t("page.instrumentAuthoring.boundary") }}
    </p>
    <p class="mb-3">
      <a :href="guide" target="_blank" rel="noopener noreferrer" class="underline" data-testid="authoring-local-guide">{{ $t("page.instrumentAuthoring.browserGuide") }}</a>
    </p>
    <n-space class="mb-3">
      <n-button v-if="instance.aiEnabled" :disabled="busy" @click="openCreate">
        {{ $t("page.instrumentAuthoring.authorize") }}
      </n-button>
      <n-button :loading="busy" :disabled="!resourceId" @click="guarded(() => refresh())">
        {{ $t("common.refresh") }}
      </n-button>
    </n-space>
    <p v-if="!instance.aiEnabled">
      {{ $t("page.instrumentAuthoring.aiOff") }}
    </p>
    <n-form-item :label="$t('page.instrumentIntegration.equipment')">
      <n-select v-model:value="resourceId" :options="equipmentOptions" :disabled="busy" />
    </n-form-item>
    <n-empty v-if="resourceId && !busy && !items.length" :description="$t('page.instrumentAuthoring.empty')" />
    <article v-for="item in items" :key="item.id" class="mb-3 min-w-0 border rounded-lg p-3">
      <div class="flex flex-wrap items-center gap-3">
        <strong class="min-w-0 break-words">{{ item.goal }}</strong>
        <n-tag>{{ $t(`page.instrumentAuthoring.state.${item.state}`) }}</n-tag>
        <n-button size="small" :disabled="busy" @click="guarded(() => inspect(item.id))">
          {{ $t("page.resourceLibrary.adapterInspect") }}
        </n-button>
      </div>
      <p>{{ $t("page.resourceLibrary.pairingExpiry") }} {{ new Date(item.expires_at).toLocaleString() }}</p>
    </article>
    <n-button v-if="more" :loading="busy" @click="guarded(() => refresh(true))">
      {{ $t("page.resourceLibrary.installMore") }}
    </n-button>

    <n-modal v-model:show="createVisible" preset="card" class="aira-dialog" style="--aira-dialog-width: 54rem" :title="$t('page.instrumentAuthoring.authorize')" :mask-closable="false" :closable="!busy" :close-on-esc="!busy">
      <n-alert type="warning" class="mb-4">
        {{ $t("page.instrumentAuthoring.requestHint") }}
      </n-alert>
      <n-form label-placement="top" :disabled="busy || !!previewDigest">
        <n-form-item :label="$t('page.instrumentAuthoring.request')" required>
          <div class="min-w-0 w-full">
            <n-button class="mb-2" :disabled="busy || !!previewDigest" @click="fileInput?.click()">
              {{ $t("page.instrumentIntegration.import") }}
            </n-button>
            <input ref="fileInput" type="file" accept=".json,application/json" class="hidden" @change="guarded(() => importFile($event))">
            <n-input v-model:value="text" type="textarea" :autosize="{ minRows: 4, maxRows: 9 }" data-testid="authoring-request" />
            <p v-if="text && !parsed" role="alert">
              {{ $t("page.instrumentAuthoring.invalid") }}
            </p>
          </div>
        </n-form-item>
        <template v-if="parsed">
          <p class="break-words">
            {{ parsed.spec.goal }}
          </p>
          <p>{{ equipmentOptions.find(item => item.value === parsed?.resource_id)?.label }}</p>
          <code class="block break-all text-xs">{{ parsed.fingerprint }}</code>
          <p>{{ $t("page.instrumentAuthoring.limits", { calls: parsed.max_iterations, seconds: parsed.duration_seconds }) }}</p>
          <instrument-source-review :commands="serverReview?.commands || parsed.spec.manifest.commands" />
          <n-collapse class="my-3">
            <n-collapse-item :title="$t('page.instrumentAuthoring.reviewInputs')">
              <pre class="max-h-96 overflow-auto whitespace-pre-wrap break-all text-xs">{{ JSON.stringify(parsed.spec, null, 2) }}</pre>
              <pre class="whitespace-pre-wrap break-all text-xs">{{ JSON.stringify(parsed.sandbox, null, 2) }}</pre>
            </n-collapse-item>
          </n-collapse>
        </template>
        <n-form-item :label="$t('page.instrumentIntegration.reason')" required>
          <n-input v-model:value="reason" maxlength="2000" />
        </n-form-item>
        <n-checkbox v-model:checked="fingerprintConfirmed" class="mb-3">
          {{ $t("page.instrumentAuthoring.fingerprintConfirm") }}
        </n-checkbox>
        <n-checkbox v-model:checked="consent">
          {{ $t("page.instrumentAuthoring.consent") }}
        </n-checkbox>
        <n-checkbox v-if="needsControlledConsent" v-model:checked="controlledConsent" class="mt-3" data-testid="authoring-controlled-consent">
          {{ $t("page.instrumentAuthoring.controlledConsent") }}
        </n-checkbox>
      </n-form>
      <n-alert v-if="previewDigest" type="warning" class="mt-4">
        {{ $t("page.instrumentAuthoring.preview") }}
      </n-alert>
      <div class="mt-4 flex flex-wrap justify-end gap-3">
        <n-button v-if="previewDigest" :disabled="busy" @click="previewDigest = ''">
          {{ $t("common.edit") }}
        </n-button>
        <n-button type="primary" :loading="busy" :disabled="!instance.aiEnabled || !parsed || !consent || !fingerprintConfirmed || !reason.trim() || (needsControlledConsent && !controlledConsent)" @click="guarded(authorize)">
          {{ $t(previewDigest ? 'common.confirm' : 'common.preview') }}
        </n-button>
      </div>
    </n-modal>

    <n-modal :show="!!selected" preset="card" class="aira-dialog" style="--aira-dialog-width: 56rem" :title="$t('page.instrumentAuthoring.history')" :mask-closable="false" :closable="!busy" :close-on-esc="!busy" @update:show="value => { if (!value) selected = null }">
      <template v-if="selected">
        <p>{{ selected.request.spec.goal }}</p>
        <code class="block break-all text-xs">{{ selected.request.fingerprint }}</code>
        <p>{{ $t(`page.instrumentAuthoring.state.${selected.effective_state}`) }} · {{ new Date(selected.expires_at).toLocaleString() }}</p>
        <instrument-source-review :commands="selected.source_review?.commands || selected.request.spec.manifest.commands" />
        <n-alert type="info" class="my-3">
          {{ $t("page.instrumentAuthoring.next") }}
        </n-alert>
        <n-button :loading="busy" @click="guarded(() => inspect(selected!.id))">
          {{ $t("common.refresh") }}
        </n-button>
        <n-empty v-if="!selected.turns.length" class="my-4" :description="$t('page.instrumentAuthoring.waiting')" />
        <article v-for="turn in selected.turns" :key="turn.id" class="my-4 min-w-0 border rounded-lg p-3">
          <h4>{{ $t("page.instrumentAuthoring.attempt", { number: turn.ordinal }) }} · {{ $t(`page.instrumentAuthoring.state.${turn.effective_state}`) }}</h4>
          <p v-if="turn.proposal">
            {{ turn.proposal.summary }}
          </p>
          <p v-if="turn.error" class="break-words">
            {{ $t("page.instrumentAuthoring.failed") }} <code>{{ turn.error }}</code>
          </p>
          <ul v-if="turn.proposal?.missing_information.length">
            <li v-for="question in turn.proposal.missing_information" :key="question" class="break-words">
              {{ question }}
            </li>
          </ul>
          <n-alert v-if="turn.report" :type="turn.report.passed ? 'info' : 'warning'" class="my-3">
            {{ $t(turn.report.passed ? 'page.instrumentAuthoring.testPassed' : 'page.instrumentAuthoring.testFailed') }}
          </n-alert>
          <n-collapse>
            <n-collapse-item :title="$t('page.instrumentAuthoring.sourceReport')">
              <pre class="max-h-96 overflow-auto whitespace-pre-wrap break-all text-xs">{{ JSON.stringify({ proposal: turn.proposal, report: turn.report }, null, 2) }}</pre>
            </n-collapse-item>
          </n-collapse>
        </article>
        <div v-if="selected.effective_state === 'open'" class="mt-4 border-t pt-4">
          <p>{{ $t("page.instrumentAuthoring.cancelHint") }}</p>
          <n-input v-model:value="cancelReason" :placeholder="$t('page.instrumentIntegration.reason')" :disabled="busy" maxlength="2000" />
          <n-checkbox v-model:checked="cancelConfirmed" class="my-3" :disabled="busy">
            {{ $t("page.instrumentAuthoring.cancelConfirm") }}
          </n-checkbox>
          <n-button type="warning" :disabled="!cancelReason.trim() || !cancelConfirmed" :loading="busy" @click="guarded(cancel)">
            {{ $t("page.instrumentAuthoring.cancel") }}
          </n-button>
        </div>
      </template>
    </n-modal>
  </section>
</template>
