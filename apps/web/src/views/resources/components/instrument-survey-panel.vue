<script setup lang="ts">
import type { SurveyReport, SurveySession, SurveySummary } from "@/service/api/instrument-surveys"
import { analyzeSurvey, cancelSurvey, confirmSurvey, exportSurvey, getSurvey, listSurveys, previewSurvey } from "@/service/api/instrument-surveys"
import { useInstanceStore } from "@/store/modules/instance"
import { $t } from "@airalogy/shared/locales"

const props = defineProps<{ gatewayId: string, equipmentOptions: Array<{ label: string, value: string }> }>()
const instance = useInstanceStore()
const resourceId = ref(props.equipmentOptions.length === 1 ? props.equipmentOptions[0].value : "")
const items = ref<SurveySummary[]>([])
const more = ref(false)
const offset = ref(0)
const busy = ref(false)
const generating = ref(false)
const createVisible = ref(false)
const text = ref("")
const goal = ref("")
const reason = ref("")
const consent = ref(false)
const reviewed = ref(false)
const preview = ref<{ preview_digest: string, capture_digest: string } | null>(null)
const requestId = ref("")
const selected = ref<SurveySession | null>(null)
const cancelReason = ref("")
const cancelConfirmed = ref(false)
const fileInput = ref<HTMLInputElement>()
const turnIds = new Map<string, string>()
const parsed = computed<SurveyReport | null>(() => {
  try {
    if (new TextEncoder().encode(text.value).length > 131072 || /(?:aiinterface|aiauthor|aiinstall|aigw)_[\w-]{43}/.test(text.value))
      return null
    const value = JSON.parse(text.value)
    if (!value || Object.keys(value).sort().join(",") !== "capture_values,controls,id,limitations,omitted_private,preview_digest,schema,target" || value.schema !== "airalogy.interface-survey.v1" || !value.target?.application || !Array.isArray(value.controls) || value.controls.length > 64 || !Array.isArray(value.limitations))
      return null
    return value
  }
  catch { return null }
})
watch([text, goal, reason, consent, reviewed, resourceId], () => {
  preview.value = null
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
  const target = resourceId.value
  const response = await listSurveys(props.gatewayId, target, append ? offset.value : 0)
  if (target !== resourceId.value)
    return
  items.value = append ? [...items.value, ...response.items] : response.items
  more.value = response.has_more
  offset.value = response.next_offset
}
watch(resourceId, () => guarded(() => refresh()))
onMounted(() => guarded(() => refresh()))
function openCreate() {
  text.value = goal.value = reason.value = ""
  consent.value = reviewed.value = false
  preview.value = null
  requestId.value = crypto.randomUUID()
  createVisible.value = true
}
async function importFile(event: Event) {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  target.value = ""
  if (!file)
    return
  if (file.size > 131072) {
    window.$message?.error($t("page.instrumentSurvey.invalid"))
    return
  }
  text.value = await file.text()
}
async function inspect(id: string) {
  selected.value = await getSurvey(id)
  cancelReason.value = ""
  cancelConfirmed.value = false
}
async function authorize() {
  if (!parsed.value || !resourceId.value || !goal.value.trim() || !reason.value.trim() || !consent.value || !reviewed.value)
    return
  const draft = { id: requestId.value, gateway_id: props.gatewayId, resource_id: resourceId.value, goal: goal.value, report: parsed.value, reason: reason.value, model_processing_consent: consent.value, capture_reviewed: reviewed.value }
  if (!preview.value) {
    preview.value = await previewSurvey(draft)
    return
  }
  const created = await confirmSurvey({ ...draft, preview_digest: preview.value.preview_digest })
  createVisible.value = false
  await inspect(created.id)
  await refresh()
}
async function analyze() {
  if (!selected.value?.can_analyze || generating.value || !instance.aiEnabled)
    return
  const id = selected.value.id
  const turnId = turnIds.get(id) || crypto.randomUUID()
  turnIds.set(id, turnId)
  generating.value = true
  selected.value.can_analyze = false
  try {
    await analyzeSurvey(id, turnId)
  }
  catch { window.$message?.warning($t("page.instrumentSurvey.uncertain")) }
  finally {
    generating.value = false
    // Read-only recovery; never spend another call after a lost response.
    await guarded(async () => {
      if (selected.value?.id === id)
        selected.value = await getSurvey(id)
      await refresh()
    })
  }
}
async function cancel() {
  if (!selected.value || !cancelReason.value.trim() || !cancelConfirmed.value)
    return
  await cancelSurvey(selected.value.id, selected.value.request.fingerprint, cancelReason.value)
  selected.value = await getSurvey(selected.value.id)
  await refresh()
}
async function download() {
  if (!selected.value)
    return
  const data = await exportSurvey(selected.value.id)
  const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }))
  const link = document.createElement("a")
  link.href = url
  link.download = `instrument-survey-${data.session_id}.json`
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
</script>

<template>
  <section class="my-6 min-w-0 border-t pt-4" data-testid="instrument-survey-panel">
    <h3>{{ $t("page.instrumentSurvey.title") }}</h3>
    <p class="my-3">
      {{ $t("page.instrumentSurvey.boundary") }}
    </p>
    <p class="my-3">
      {{ $t("page.instrumentSurvey.local") }}
    </p>
    <n-form-item :label="$t('page.instrumentIntegration.equipment')">
      <n-select v-model:value="resourceId" :options="equipmentOptions" :disabled="busy || generating || createVisible || !!selected" />
    </n-form-item>
    <n-space class="mb-3">
      <n-button v-if="instance.aiEnabled" :disabled="busy || generating || !resourceId" @click="openCreate">
        {{ $t("page.instrumentSurvey.authorize") }}
      </n-button>
      <n-button :loading="busy" :disabled="!resourceId" @click="guarded(() => refresh())">
        {{ $t("common.refresh") }}
      </n-button>
    </n-space>
    <p v-if="!instance.aiEnabled">
      {{ $t("page.instrumentSurvey.aiOff") }}
    </p>
    <n-empty v-if="resourceId && !busy && !items.length" :description="$t('page.instrumentSurvey.empty')" />
    <article v-for="item in items" :key="item.id" class="mb-3 min-w-0 border rounded-lg p-3">
      <div class="flex flex-wrap items-center gap-3">
        <strong class="min-w-0 break-words">{{ item.goal }}</strong>
        <n-tag>{{ $t(`page.instrumentExploration.state.${item.state}`) }}</n-tag>
        <n-button size="small" :disabled="busy" @click="guarded(() => inspect(item.id))">
          {{ $t("page.resourceLibrary.adapterInspect") }}
        </n-button>
      </div>
    </article>
    <n-button v-if="more" :loading="busy" @click="guarded(() => refresh(true))">
      {{ $t("page.resourceLibrary.installMore") }}
    </n-button>

    <n-modal v-model:show="createVisible" preset="card" class="aira-dialog" style="--aira-dialog-width: 54rem" :title="$t('page.instrumentSurvey.authorize')" :mask-closable="false" :closable="!busy" :close-on-esc="!busy">
      <n-alert type="warning" class="mb-4">
        {{ $t("page.instrumentSurvey.reportHint") }}
      </n-alert>
      <n-form label-placement="top" :disabled="busy">
        <n-form-item :label="$t('page.instrumentSurvey.report')" required>
          <div class="min-w-0 w-full">
            <n-button class="mb-2" :disabled="busy || !!preview" @click="fileInput?.click()">
              {{ $t("page.instrumentIntegration.import") }}
            </n-button>
            <input ref="fileInput" type="file" accept=".json,application/json" class="hidden" @change="guarded(() => importFile($event))">
            <n-input v-model:value="text" type="textarea" :readonly="!!preview" :autosize="{ minRows: 4, maxRows: 8 }" data-testid="survey-report" />
            <p v-if="text && !parsed" role="alert">
              {{ $t("page.instrumentSurvey.invalid") }}
            </p>
          </div>
        </n-form-item>
        <p v-if="parsed" class="break-words">
          {{ parsed.target.application }} · {{ parsed.target.version }} · {{ parsed.controls.length }}
        </p>
        <n-form-item :label="$t('page.instrumentSurvey.goal')" required>
          <n-input v-model:value="goal" :readonly="!!preview" maxlength="4000" data-testid="survey-goal" />
        </n-form-item>
        <n-form-item :label="$t('page.instrumentIntegration.reason')" required>
          <n-input v-model:value="reason" :readonly="!!preview" maxlength="2000" data-testid="survey-reason" />
        </n-form-item>
        <n-checkbox v-model:checked="reviewed" :disabled="!!preview" :theme-overrides="{ textColorDisabled: 'var(--n-text-color)' }" class="mb-3 block">
          {{ $t("page.instrumentSurvey.reviewed") }}
        </n-checkbox>
        <n-checkbox v-model:checked="consent" :disabled="!!preview" :theme-overrides="{ textColorDisabled: 'var(--n-text-color)' }" class="block">
          {{ $t("page.instrumentSurvey.consent") }}
        </n-checkbox>
      </n-form>
      <n-alert v-if="preview" type="warning" class="mt-4">
        {{ $t("page.instrumentSurvey.preview") }}
        <code class="mt-2 block break-all text-xs">{{ preview.capture_digest }}</code>
      </n-alert>
      <div class="mt-4 flex flex-wrap justify-end gap-3">
        <n-button v-if="preview" :disabled="busy" @click="preview = null">
          {{ $t("common.edit") }}
        </n-button>
        <n-button type="primary" :loading="busy" :disabled="!instance.aiEnabled || !parsed || !goal.trim() || !reason.trim() || !consent || !reviewed" @click="guarded(authorize)">
          {{ $t(preview ? 'common.confirm' : 'common.preview') }}
        </n-button>
      </div>
    </n-modal>

    <n-modal :show="!!selected" preset="card" class="aira-dialog" style="--aira-dialog-width: 56rem" :title="$t('page.instrumentSurvey.history')" :mask-closable="false" :closable="!busy" :close-on-esc="!busy" @update:show="value => { if (!value) selected = null }">
      <template v-if="selected">
        <p class="break-words">
          {{ selected.request.spec.goal }}
        </p>
        <p>{{ $t(`page.instrumentExploration.state.${selected.effective_state}`) }} · {{ new Date(selected.expires_at).toLocaleString() }}</p>
        <n-alert type="info" class="my-3">
          {{ $t("page.instrumentSurvey.next") }}
        </n-alert>
        <n-space>
          <n-button :loading="busy" @click="guarded(() => inspect(selected!.id))">
            {{ $t("common.refresh") }}
          </n-button>
          <n-button v-if="instance.aiEnabled && (selected.can_analyze || generating)" type="primary" :loading="generating" :disabled="busy || generating" @click="analyze">
            {{ $t("page.instrumentSurvey.analyze") }}
          </n-button>
          <n-button v-if="selected.turns.some(turn => turn.effective_state === 'generated')" :disabled="busy" @click="guarded(download)">
            {{ $t("page.instrumentSurvey.export") }}
          </n-button>
        </n-space>
        <p v-if="!selected.turns.length" class="my-3">
          {{ $t("page.instrumentSurvey.waiting") }}
        </p>
        <article v-for="turn in selected.turns" :key="turn.id" class="my-4 min-w-0 border rounded-lg p-3">
          <h4>{{ $t(`page.instrumentAuthoring.state.${turn.effective_state}`) }}</h4>
          <p v-if="turn.error">
            {{ $t("page.instrumentSurvey.uncertain") }} <code>{{ turn.error }}</code>
          </p>
          <template v-if="turn.proposal">
            <p class="my-3 break-words">
              {{ turn.proposal.summary }}
            </p>
            <p>{{ $t("page.instrumentSurvey.route") }} {{ $t(`page.instrumentSurvey.routes.${turn.proposal.route}`) }}</p>
            <div v-for="feature in turn.proposal.features" :key="feature.control_id" class="my-3 min-w-0 rounded bg-gray-50 p-3">
              <strong>{{ selected.request.spec.report.controls.find(control => control.id === feature.control_id)?.label || feature.control_id }}</strong>
              <p class="break-words">
                {{ feature.interpretation }}
              </p>
              <span>{{ $t(`page.instrumentSurvey.basis.${feature.basis}`) }} · {{ $t(`page.instrumentSurvey.risks.${feature.risk}`) }}</span>
            </div>
            <ul class="my-3 list-disc pl-5">
              <li v-for="note in [...turn.proposal.limitations, ...turn.proposal.missing_information]" :key="note" class="break-words">
                {{ note }}
              </li>
            </ul>
          </template>
        </article>
        <n-collapse class="my-3">
          <n-collapse-item :title="$t('page.instrumentSurvey.report')">
            <pre class="max-h-96 overflow-auto whitespace-pre-wrap break-all text-xs">{{ JSON.stringify(selected.request.spec.report, null, 2) }}</pre>
          </n-collapse-item>
        </n-collapse>
        <div v-if="selected.effective_state === 'open'" class="mt-4 border-t pt-4">
          <p>{{ $t("page.instrumentSurvey.cancelHint") }}</p>
          <n-input v-model:value="cancelReason" :placeholder="$t('page.instrumentIntegration.reason')" :disabled="busy" maxlength="2000" />
          <n-checkbox v-model:checked="cancelConfirmed" class="my-3" :disabled="busy">
            {{ $t("page.instrumentSurvey.cancelConfirm") }}
          </n-checkbox>
          <n-button type="warning" :disabled="!cancelReason.trim() || !cancelConfirmed" :loading="busy" @click="guarded(cancel)">
            {{ $t("page.instrumentAuthoring.cancel") }}
          </n-button>
        </div>
      </template>
    </n-modal>
  </section>
</template>
