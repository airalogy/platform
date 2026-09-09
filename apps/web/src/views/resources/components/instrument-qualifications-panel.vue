<script setup lang="ts">
import type { QualificationCheck, QualificationCheckKind, QualificationContext, QualificationPreview, QualificationRecord, QualificationReport, QualificationScope } from "@/service/api/instrument-qualifications"
import { confirmQualification, confirmQualificationRevocation, fetchQualificationContext, fetchQualifications, previewQualification, previewQualificationRevocation } from "@/service/api/instrument-qualifications"
import { $t } from "@airalogy/shared/locales"

const props = defineProps<{ bindingId: string, installed: boolean }>()
const busy = ref(false)
const error = ref(false)
const rows = ref<QualificationRecord[]>([])
const more = ref(false)
const offset = ref(0)
const open = ref(false)
const context = ref<QualificationContext | null>(null)
const preview = ref<QualificationPreview | null>(null)
const prepared = ref<QualificationReport | null>(null)
const scope = ref<QualificationScope>("simulation")
const origin = ref<QualificationReport["evidence_origin"]>("manual_observation")
const target = reactive<QualificationReport["target"]>({ identity_reference: "", firmware: "", application: "", application_version: "", driver_version: "", os_version: "" })
const targetKeys = Object.keys(target) as (keyof typeof target)[]
const chosen = ref<string[]>([])
const assessments = reactive<Record<string, QualificationCheck[]>>({})
const assessedAt = ref<number | null>(null)
const expiresAt = ref<number | null>(null)
const reason = ref("")
const reviewed = ref(false)
const authorized = ref(false)
const revokeId = ref("")
const revokeReason = ref("")
const revokeDigest = ref("")
const selected = computed(() => (context.value?.commands || []).filter(command => chosen.value.includes(`${command.key}@${command.version}`)))
const scopeOptions = computed(() => (["simulation", "read_only", "controlled"] as const).map(value => ({ value, label: $t(`page.resourceLibrary.qualification.scope.${value}`), disabled: value !== "simulation" && !context.value?.commands.some(command => !command.simulation_only) })))
const commandOptions = computed(() => (context.value?.commands || []).map(item => ({ value: `${item.key}@${item.version}`, label: `${item.name} · ${item.version}`, disabled: (scope.value !== "simulation" && item.simulation_only) || (scope.value === "read_only" && item.risk !== "read_only") })))
watch(scope, () => {
  if (!preview.value)
    chosen.value = chosen.value.filter(value => commandOptions.value.some(option => option.value === value && !option.disabled))
})
const complete = computed(() => targetKeys.every(key => target[key].trim()) && reason.value.trim() && assessedAt.value && expiresAt.value && selected.value.length && selected.value.every(command => assessments[`${command.key}@${command.version}`]?.every(check => check.method.trim() && check.expected.trim() && check.observed.trim())) && (scope.value === "simulation" || (reviewed.value && authorized.value)))
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
  const result = await fetchQualifications(props.bindingId, append ? offset.value : 0)
  rows.value = append ? [...rows.value, ...result.items] : result.items
  offset.value = result.next_offset
  more.value = result.has_more
}
async function create() {
  context.value = await fetchQualificationContext(props.bindingId)
  preview.value = null
  prepared.value = null
  scope.value = "simulation"
  origin.value = "manual_observation"
  targetKeys.forEach(key => target[key] = "")
  reason.value = ""
  reviewed.value = false
  authorized.value = false
  assessedAt.value = Date.now()
  expiresAt.value = Date.now() + 30 * 86400000
  chosen.value = context.value.commands.length === 1 ? [`${context.value.commands[0].key}@${context.value.commands[0].version}`] : []
  for (const command of context.value.commands) {
    const kinds: QualificationCheckKind[] = ["identity", "output", "completion"]
    if (command.risk !== "read_only")
      kinds.push("parameter_readback", "safe_stop", "manual_takeover", "interlocks")
    assessments[`${command.key}@${command.version}`] = kinds.map(kind => ({ kind, method: "", expected: "", observed: "", passed: false }))
  }
  open.value = true
}
async function save() {
  if (!preview.value) {
    prepared.value = { id: crypto.randomUUID(), scope: scope.value, evidence_origin: origin.value, target: { ...target }, commands: selected.value.map(command => ({ key: command.key, version: command.version, checks: assessments[`${command.key}@${command.version}`].map(check => ({ ...check })) })), evidence_file_ids: [], assessed_at: new Date(assessedAt.value!).toISOString(), expires_at: new Date(expiresAt.value!).toISOString(), reason: reason.value, independent_review_confirmed: reviewed.value, physical_tests_authorized: authorized.value }
    preview.value = await previewQualification(props.bindingId, prepared.value)
    return
  }
  await confirmQualification(props.bindingId, prepared.value!, preview.value.preview_digest)
  open.value = false
  await refresh()
  window.$message?.success($t("page.resourceLibrary.qualification.saved"))
}
async function revoke() {
  if (!revokeDigest.value) {
    revokeDigest.value = (await previewQualificationRevocation(props.bindingId, revokeId.value, revokeReason.value)).preview_digest
    return
  }
  await confirmQualificationRevocation(props.bindingId, revokeId.value, revokeReason.value, revokeDigest.value)
  revokeId.value = ""
  await refresh()
}
onMounted(() => guarded(() => refresh()))
</script>

<template>
  <section class="my-5 min-w-0" data-testid="instrument-qualifications">
    <h3>{{ $t("page.resourceLibrary.qualification.title") }}</h3>
    <p class="my-3">
      {{ $t("page.resourceLibrary.qualification.hint") }}
    </p>
    <n-alert v-if="error" type="error" class="my-3">
      {{ $t("page.resourceLibrary.qualification.retry") }}
    </n-alert>
    <n-space class="mb-3">
      <n-button :disabled="!installed || busy" @click="guarded(create)">
        {{ $t("page.resourceLibrary.qualification.create") }}
      </n-button>
      <n-button :loading="busy" @click="guarded(() => refresh())">
        {{ $t("common.refresh") }}
      </n-button>
    </n-space>
    <p v-if="!rows.length">
      {{ $t("page.resourceLibrary.qualification.empty") }}
    </p>
    <article v-for="row in rows" :key="row.id" class="my-3 border border-gray-200 rounded p-3">
      <strong>{{ $t(`page.resourceLibrary.qualification.state.${row.effective_state}`) }}</strong>
      <p class="my-2">
        {{ $t(`page.resourceLibrary.qualification.scope.${row.scope}`) }} · {{ $t('page.resourceLibrary.qualification.expiresAt') }}: {{ new Date(row.expires_at).toLocaleString() }}
      </p>
      <p v-if="row.details_redacted">
        {{ $t("page.resourceLibrary.qualification.redacted") }}
      </p>
      <details v-if="row.report" class="mb-3">
        <summary>{{ $t("page.resourceLibrary.qualification.details") }}</summary>
        <p v-if="row.assessor && row.assessed_at" class="my-2 break-words">
          {{ row.assessor.name }} · {{ new Date(row.assessed_at).toLocaleString() }}
        </p>
        <p v-for="key in targetKeys" :key="key" class="my-2 break-words">
          {{ $t(`page.resourceLibrary.qualification.target.${key}`) }}: {{ row.report.target[key] }}
        </p>
        <p class="my-2 break-words">
          {{ row.report.reason }}
        </p>
        <div v-for="command in row.report.commands" :key="`${command.key}@${command.version}`" class="my-3">
          <code class="break-all">{{ command.key }}@{{ command.version }}</code>
          <p v-for="check in command.checks" :key="check.kind" class="my-2 whitespace-pre-wrap break-words">
            {{ $t(`page.resourceLibrary.qualification.check.${check.kind}`) }} · {{ check.passed ? $t('page.resourceLibrary.qualification.passed') : $t('page.resourceLibrary.qualification.state.failed') }}<br>
            {{ $t("page.resourceLibrary.qualification.method") }}: {{ check.method }}<br>
            {{ $t("page.resourceLibrary.qualification.expected") }}: {{ check.expected }}<br>
            {{ $t("page.resourceLibrary.qualification.observed") }}: {{ check.observed }}
          </p>
        </div>
      </details>
      <n-button v-if="!row.revoked_at" :disabled="busy" @click="revokeId = row.id; revokeReason = ''; revokeDigest = ''">
        {{ $t("page.resourceLibrary.qualification.revoke") }}
      </n-button>
    </article>
    <n-button v-if="more" :loading="busy" @click="guarded(() => refresh(true))">
      {{ $t("page.resourceLibrary.installMore") }}
    </n-button>
    <n-modal v-model:show="open" preset="card" class="aira-dialog" style="--aira-dialog-width: 56rem" :title="$t('page.resourceLibrary.qualification.create')" :mask-closable="false">
      <n-alert type="info" class="mb-3">
        {{ $t("page.resourceLibrary.qualification.hint") }}
      </n-alert>
      <n-alert v-if="error" type="error" class="mb-3">
        {{ $t("page.resourceLibrary.qualification.retry") }}
      </n-alert>
      <n-form label-placement="top" :disabled="busy || !!preview">
        <n-form-item :label="$t('page.resourceLibrary.qualification.scopeLabel')" required>
          <n-select v-model:value="scope" :options="scopeOptions" />
        </n-form-item>
        <n-form-item :label="$t('page.resourceLibrary.qualification.originLabel')" required>
          <n-select v-model:value="origin" :options="(['manual_observation', 'independent_test', 'package_self_test'] as const).map(value => ({ value, label: $t(`page.resourceLibrary.qualification.origin.${value}`) }))" />
        </n-form-item>
        <n-form-item v-for="key in targetKeys" :key="key" :label="$t(`page.resourceLibrary.qualification.target.${key}`)" required>
          <n-input v-model:value="target[key]" :maxlength="255" :data-testid="`qualification-${key}`" />
        </n-form-item>
        <div class="grid gap-3 sm:grid-cols-2">
          <n-form-item :label="$t('page.resourceLibrary.qualification.assessedAt')" required>
            <n-date-picker v-model:value="assessedAt" type="datetime" />
          </n-form-item>
          <n-form-item :label="$t('page.resourceLibrary.qualification.expiresAt')" required>
            <n-date-picker v-model:value="expiresAt" type="datetime" />
          </n-form-item>
        </div>
        <n-form-item :label="$t('page.resourceLibrary.qualification.commands')" required>
          <n-select v-model:value="chosen" multiple :options="commandOptions" />
        </n-form-item>
        <div v-for="command in selected" :key="`${command.key}@${command.version}`" class="mb-4 border border-gray-200 rounded p-3">
          <h4>{{ command.name }} · {{ command.version }}</h4>
          <div v-for="check in assessments[`${command.key}@${command.version}`]" :key="check.kind" class="mt-4" :data-testid="`qualification-check-${check.kind}`">
            <h5 class="mb-2">
              {{ $t(`page.resourceLibrary.qualification.check.${check.kind}`) }}
            </h5>
            <n-form-item :label="$t('page.resourceLibrary.qualification.method')" required>
              <n-input v-model:value="check.method" :maxlength="1000" />
            </n-form-item>
            <n-form-item :label="$t('page.resourceLibrary.qualification.expected')" required>
              <n-input v-model:value="check.expected" type="textarea" :rows="2" :maxlength="1000" />
            </n-form-item>
            <n-form-item :label="$t('page.resourceLibrary.qualification.observed')" required>
              <n-input v-model:value="check.observed" type="textarea" :rows="2" :maxlength="1000" />
            </n-form-item>
            <n-checkbox v-model:checked="check.passed">
              {{ $t("page.resourceLibrary.qualification.passed") }}
            </n-checkbox>
          </div>
        </div>
        <n-form-item :label="$t('page.resourceLibrary.changeReason')" required>
          <n-input v-model:value="reason" type="textarea" :maxlength="2000" data-testid="qualification-reason" />
        </n-form-item>
        <template v-if="scope !== 'simulation'">
          <n-checkbox v-model:checked="reviewed" class="mb-3">
            {{ $t("page.resourceLibrary.qualification.reviewed") }}
          </n-checkbox>
          <n-checkbox v-model:checked="authorized">
            {{ $t("page.resourceLibrary.qualification.authorized") }}
          </n-checkbox>
        </template>
      </n-form>
      <n-alert v-if="preview" type="warning" class="my-3">
        {{ $t("page.resourceLibrary.qualification.impact") }}
      </n-alert>
      <pre v-if="preview" class="max-h-64 overflow-auto whitespace-pre-wrap break-all text-xs">{{ JSON.stringify(preview.pins, null, 2) }}</pre>
      <template #footer>
        <n-space justify="end">
          <n-button :disabled="busy" @click="open = false">
            {{ $t("common.cancel") }}
          </n-button>
          <n-button v-if="preview" :disabled="busy" @click="preview = null">
            {{ $t("common.previous") }}
          </n-button>
          <n-button type="primary" :loading="busy" :disabled="!complete" @click="guarded(save)">
            {{ preview ? $t("common.confirm") : $t("common.preview") }}
          </n-button>
        </n-space>
      </template>
    </n-modal>
    <n-modal :show="!!revokeId" preset="card" class="aira-dialog" :title="$t('page.resourceLibrary.qualification.revoke')" :mask-closable="false" @update:show="revokeId = ''">
      <n-alert type="warning" class="mb-3">
        {{ $t("page.resourceLibrary.qualification.revokeHint") }}
      </n-alert>
      <n-alert v-if="error" type="error" class="mb-3">
        {{ $t("page.resourceLibrary.qualification.retry") }}
      </n-alert>
      <n-input v-model:value="revokeReason" type="textarea" :disabled="busy || !!revokeDigest" :maxlength="2000" />
      <template #footer>
        <n-space justify="end">
          <n-button :disabled="busy" @click="revokeId = ''">
            {{ $t("common.cancel") }}
          </n-button>
          <n-button v-if="revokeDigest" :disabled="busy" @click="revokeDigest = ''">
            {{ $t("common.previous") }}
          </n-button>
          <n-button :loading="busy" :disabled="!revokeReason.trim()" @click="guarded(revoke)">
            {{ revokeDigest ? $t("common.confirm") : $t("common.preview") }}
          </n-button>
        </n-space>
      </template>
    </n-modal>
  </section>
</template>
