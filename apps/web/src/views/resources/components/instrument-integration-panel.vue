<template>
  <section class="mt-6 border-t pt-5" data-testid="instrument-integration-panel">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h3 class="m-0">
          {{ $t("page.instrumentIntegration.title") }}
        </h3>
        <p class="text-sm text-gray-500">
          {{ $t("page.instrumentIntegration.subtitle") }}
        </p>
      </div>
      <n-button @click="openEditor()">
        {{ $t("page.instrumentIntegration.newDraft") }}
      </n-button>
    </div>
    <n-alert type="warning" class="mb-4">
      {{ $t("page.instrumentIntegration.boundary") }}
    </n-alert>
    <operation-feedback v-if="loadError" class="mb-3" />
    <n-spin :show="loading">
      <n-empty v-if="!items.length" :description="$t('page.instrumentIntegration.empty')" />
      <div v-for="item in items" :key="item.id" class="mb-3 flex flex-wrap items-center justify-between gap-3 border rounded-lg p-3">
        <div class="min-w-0 flex-1">
          <div class="break-words font-medium">
            {{ item.goal }}
          </div>
          <div class="mt-1 text-sm text-gray-500">
            {{ equipmentName(item.resource_id) }} · v{{ item.revision }}
          </div>
          <n-tag size="small" class="mt-2" :type="item.report.passed ? 'info' : 'warning'">
            {{ $t(item.report.passed ? "page.instrumentIntegration.simulated" : "page.instrumentIntegration.needsReview") }}
          </n-tag>
        </div>
        <div class="flex flex-wrap gap-2">
          <n-button size="small" @click="openEditor(item)">
            {{ $t("common.edit") }}
          </n-button>
          <n-button size="small" @click="exportBundle(item.bundle)">
            {{ $t("page.instrumentIntegration.export") }}
          </n-button>
          <n-button size="small" @click="openHistory(item)">
            {{ $t("page.instrumentIntegration.history") }}
          </n-button>
        </div>
      </div>
    </n-spin>

    <n-modal v-model:show="visible" preset="card" class="aira-dialog" style="--aira-dialog-width: 64rem" :mask-closable="false" :close-on-esc="!busy" :closable="!busy" :title="$t('page.instrumentIntegration.title')">
      <operation-feedback v-if="error" class="mb-3" :message="error" :uncertain="uncertain" />
      <n-form label-placement="top" :disabled="busy || !!preview">
        <n-form-item :label="$t('page.instrumentIntegration.equipment')" required>
          <n-select v-model:value="form.resource_id" :options="equipmentOptions" :disabled="form.expected_revision > 0 || busy || !!preview" data-testid="integration-equipment" />
        </n-form-item>
        <n-form-item :label="$t('page.instrumentIntegration.goal')" required>
          <n-input v-model:value="form.goal" maxlength="4000" data-testid="integration-goal" />
        </n-form-item>
        <n-form-item :label="$t('page.instrumentIntegration.bundle')" required>
          <div class="min-w-0 w-full">
            <div class="mb-2 flex flex-wrap gap-2">
              <n-button size="small" :disabled="busy || !!preview" @click="loadExample">
                {{ $t("page.instrumentIntegration.example") }}
              </n-button>
              <n-button size="small" :disabled="busy || !!preview" @click="fileInput?.click()">
                {{ $t("page.instrumentIntegration.import") }}
              </n-button>
              <input ref="fileInput" type="file" accept=".json,application/json" class="hidden" @change="importBundle">
            </div>
            <n-input v-model:value="bundleText" type="textarea" :autosize="{ minRows: 8, maxRows: 16 }" class="font-mono" data-testid="integration-bundle" />
            <p class="text-xs text-gray-500">
              {{ $t("page.instrumentIntegration.bundleHint") }}
            </p>
          </div>
        </n-form-item>
        <n-form-item :label="$t('page.instrumentIntegration.reason')" required>
          <n-input v-model:value="form.reason" maxlength="2000" data-testid="integration-reason" />
        </n-form-item>
        <template v-if="instanceStore.aiEnabled && !preview">
          <n-form-item :label="$t('page.instrumentIntegration.notes')">
            <n-input v-model:value="notes" type="textarea" maxlength="20000" />
          </n-form-item>
          <n-checkbox v-model:checked="consent">
            {{ $t("page.instrumentIntegration.consent") }}
          </n-checkbox>
          <n-button class="mt-3" :disabled="!consent || busy" :loading="generating" @click="generate">
            {{ $t("page.instrumentIntegration.aira") }}
          </n-button>
        </template>
      </n-form>
      <div v-if="preview" class="mt-4" data-testid="integration-preview">
        <n-alert :type="preview.report.passed ? 'info' : 'warning'" :title="$t(preview.report.passed ? 'page.instrumentIntegration.simulated' : 'page.instrumentIntegration.needsReview')">
          {{ $t("page.instrumentIntegration.saveHint") }}
        </n-alert>
        <p class="break-all text-sm">
          {{ equipmentName(form.resource_id) }} · {{ gatewayName }}
        </p>
        <p class="break-all text-xs text-gray-500">
          SHA-256: {{ preview.content_digest }}
        </p>
        <ul>
          <li v-for="item in preview.report.cases" :key="item.name">
            {{ item.name }} — {{ item.passed ? $t("page.instrumentIntegration.matched") : `${item.failure?.step}: ${item.failure?.reason}` }}
          </li>
        </ul>
        <p v-if="preview.report.uncovered_commands.length">
          {{ $t("page.instrumentIntegration.uncovered") }}: {{ preview.report.uncovered_commands.join(", ") }}
        </p>
      </div>
      <template #footer>
        <div class="flex flex-wrap justify-end gap-2">
          <n-button :disabled="busy" @click="preview ? preview = null : visible = false">
            {{ preview ? $t("common.edit") : $t("common.cancel") }}
          </n-button>
          <n-button v-if="!preview" type="primary" :loading="busy" @click="runPreview">
            {{ $t("page.instrumentIntegration.preview") }}
          </n-button>
          <n-button v-else type="primary" :loading="busy" @click="confirm">
            {{ $t("page.instrumentIntegration.confirm") }}
          </n-button>
        </div>
      </template>
    </n-modal>

    <n-modal v-model:show="historyVisible" preset="card" class="aira-dialog" :title="$t('page.instrumentIntegration.history')">
      <p>{{ $t("page.instrumentIntegration.historyHint") }}</p>
      <div v-for="entry in history" :key="entry.id" class="mb-2 flex items-center justify-between gap-2 border-b py-2">
        <div class="min-w-0 break-words">
          v{{ entry.revision }} · {{ entry.reason }}
        </div>
        <n-button size="small" @click="exportBundle(entry.snapshot.bundle)">
          {{ $t("page.instrumentIntegration.export") }}
        </n-button>
      </div>
    </n-modal>
  </section>
</template>

<script setup lang="ts">
import type { IntegrationBundle, IntegrationPreview, SavedIntegration } from "@/service/api/instrument-integrations"
import { draftIntegrationWithAira, fetchIntegrationExample, fetchIntegrationHistory, fetchIntegrations, previewIntegration, saveIntegration } from "@/service/api/instrument-integrations"
import { useInstanceStore } from "@/store/modules/instance"
import { $t } from "@airalogy/shared/locales"

const props = defineProps<{ gatewayId: string, gatewayName: string, equipmentOptions: Array<{ label: string, value: string }> }>()
const instanceStore = useInstanceStore()
const items = ref<SavedIntegration[]>([])
const loading = ref(false)
const loadError = ref(false)
const visible = ref(false)
const busy = ref(false)
const generating = ref(false)
const error = ref("")
const uncertain = ref(false)
const preview = ref<IntegrationPreview | null>(null)
const bundleText = ref("")
const notes = ref("")
const consent = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)
const form = reactive({ id: "", resource_id: "", expected_revision: 0, goal: "", reason: "" })
const historyVisible = ref(false)
const history = ref<Awaited<ReturnType<typeof fetchIntegrationHistory>>["items"]>([])

function equipmentName(id: string) {
  return props.equipmentOptions.find(item => item.value === id)?.label || id
}

async function reload() {
  loading.value = true
  loadError.value = false
  try {
    items.value = (await fetchIntegrations(props.gatewayId)).items
  }
  catch { loadError.value = true }
  finally { loading.value = false }
}

function openEditor(item?: SavedIntegration) {
  Object.assign(form, { id: item?.id || crypto.randomUUID(), resource_id: item?.resource_id || (props.equipmentOptions.length === 1 ? props.equipmentOptions[0].value : ""), expected_revision: item?.revision || 0, goal: item?.goal || "", reason: "" })
  bundleText.value = item ? JSON.stringify(item.bundle, null, 2) : ""
  preview.value = null
  error.value = ""
  uncertain.value = false
  notes.value = ""
  consent.value = false
  visible.value = true
}

function payload() {
  if (!form.resource_id || !form.goal.trim() || !form.reason.trim())
    throw new Error($t("page.instrumentIntegration.required"))
  if (new TextEncoder().encode(bundleText.value).length > 262144)
    throw new Error($t("page.instrumentIntegration.invalidBundle"))
  let bundle: IntegrationBundle
  try {
    bundle = JSON.parse(bundleText.value)
    if (!bundle || !bundle.package || !Array.isArray(bundle.scenarios))
      throw new Error("Invalid bundle")
  }
  catch {
    throw new Error($t("page.instrumentIntegration.invalidBundle"))
  }
  return { ...form, gateway_id: props.gatewayId, bundle }
}

function failed(cause: unknown) {
  error.value = cause instanceof Error ? cause.message : $t("page.instrumentIntegration.failed")
}

async function loadExample() {
  busy.value = true
  try {
    bundleText.value = JSON.stringify(await fetchIntegrationExample(), null, 2)
  }
  catch (cause) { failed(cause) }
  finally { busy.value = false }
}

async function importBundle(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file)
    return
  try {
    if (file.size > 262144)
      throw new Error($t("page.instrumentIntegration.invalidBundle"))
    const content = await file.text()
    JSON.parse(content)
    bundleText.value = content
  }
  catch { error.value = $t("page.instrumentIntegration.invalidBundle") }
  finally { input.value = "" }
}

async function runPreview() {
  error.value = ""
  uncertain.value = false
  busy.value = true
  try {
    preview.value = await previewIntegration(payload())
  }
  catch (cause) { failed(cause) }
  finally { busy.value = false }
}

async function confirm() {
  if (!preview.value)
    return
  error.value = ""
  busy.value = true
  try {
    const saved = await saveIntegration({ ...payload(), preview_digest: preview.value.preview_digest })
    items.value = [saved, ...items.value.filter(item => item.id !== saved.id)]
    visible.value = false
    window.$message?.success($t("page.instrumentIntegration.saved"))
  }
  catch (cause) {
    uncertain.value = true
    failed(cause)
  }
  finally { busy.value = false }
}

async function generate() {
  error.value = ""
  busy.value = true
  generating.value = true
  try {
    const data = payload()
    const result = await draftIntegrationWithAira({ ...data, authorized_notes: notes.value, model_processing_consent: consent.value })
    bundleText.value = JSON.stringify({ ...data.bundle, package: result.package }, null, 2)
  }
  catch (cause) { failed(cause) }
  finally {
    busy.value = false
    generating.value = false
  }
}

function exportBundle(bundle: IntegrationBundle) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(bundle, null, 2)], { type: "application/json" }))
  const link = document.createElement("a")
  link.href = url
  link.download = "airalogy-gui-rehearsal.json"
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

async function openHistory(item: SavedIntegration) {
  loadError.value = false
  try {
    history.value = (await fetchIntegrationHistory(item.id)).items
    historyVisible.value = true
  }
  catch { loadError.value = true }
}

onMounted(reload)
</script>
