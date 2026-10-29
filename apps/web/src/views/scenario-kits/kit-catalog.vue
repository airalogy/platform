<script setup lang="ts">
import type { KitDirectory, KitOperation, KitPreview, ScenarioKit } from "@/service/api/scenario-kits"
import { confirmKit, downloadKitFile, fetchKitDirectory, fetchKitHistory, previewKit } from "@/service/api/scenario-kits"
import { computed, ref, watch } from "vue"
import { useI18n } from "vue-i18n"

const props = defineProps<{ labId: string, projectId?: string }>()
const emit = defineEmits<{ changed: [value: KitDirectory] }>()
const { t, locale } = useI18n()
const directory = ref<KitDirectory>()
const loading = ref(false)
const error = ref("")
const preview = ref<KitPreview>()
const operation = ref<KitOperation>()
const showPreview = ref(false)
const busy = ref(false)
const strategy = ref<"keep" | "new_copy">("keep")
const selectedVersions = ref<Record<string, string>>({})
const receipt = ref("")
let requestId = ""
let sequence = 0
const entries = computed(() => {
  const groups = new Map<string, ScenarioKit[]>()
  for (const kit of directory.value?.kits || [])
    groups.set(kit.id, [...(groups.get(kit.id) || []), kit])
  return [...groups.values()].map(versions => ({ versions, kit: versions.find(kit => kit.version === selectedVersions.value[kit.id]) || versions.at(-1)! }))
})
function label(values: Record<string, string>) {
  return values[locale.value] || values[locale.value.toLowerCase().startsWith("zh") ? "zh-CN" : "en-US"]
}
function errorText(value: unknown) {
  const detail = (value as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return typeof detail === "string" ? detail : value instanceof Error ? value.message : t("page.scenarioKits.failed")
}
function reason(value: string) {
  const [code, detail] = value.split(":")
  return `${t(`page.scenarioKits.blockers.${code}`)}${detail ? ` (${detail})` : ""}`
}
async function load() {
  const current = ++sequence
  loading.value = true
  error.value = ""
  directory.value = undefined
  try {
    const value = await fetchKitDirectory(props.labId, props.projectId)
    if (current !== sequence)
      return
    directory.value = value
    for (const kit of value.kits) {
      if (!selectedVersions.value[kit.id] && kit.installation)
        selectedVersions.value[kit.id] = kit.installation.version
    }
    emit("changed", value)
  }
  catch (err) {
    if (current === sequence)
      error.value = errorText(err)
  }
  finally {
    if (current === sequence)
      loading.value = false
  }
}
async function prepare(kit: ScenarioKit, action: KitOperation["action"]) {
  busy.value = true
  error.value = ""
  receipt.value = ""
  operation.value = { kit_id: kit.id, version: kit.version, action, strategy: strategy.value }
  try {
    preview.value = await previewKit(props.labId, props.projectId, operation.value)
    requestId = crypto.randomUUID()
    showPreview.value = true
  }
  catch (err) { error.value = errorText(err) }
  finally { busy.value = false }
}
async function confirm() {
  if (!operation.value || !preview.value)
    return
  busy.value = true
  error.value = ""
  try {
    const result = await confirmKit(props.labId, props.projectId, operation.value, preview.value.preview_token, requestId)
    receipt.value = result.event_id
    showPreview.value = false
    await load()
  }
  catch (err) { error.value = errorText(err) }
  finally { busy.value = false }
}
async function exportHistory() {
  try {
    const value = await fetchKitHistory(props.labId, props.projectId)
    downloadKitFile(JSON.stringify(value, null, 2), "scenario-kit-history.json", "application/json")
  }
  catch (err) { error.value = errorText(err) }
}
watch(() => [props.labId, props.projectId], () => {
  selectedVersions.value = {}
  showPreview.value = false
  receipt.value = ""
  void load()
}, { immediate: true })
</script>

<template>
  <section class="min-w-0 space-y-4" data-testid="kit-catalog">
    <h2 class="text-xl font-semibold">
      {{ t('page.scenarioKits.title') }}
    </h2>
    <p class="text-sm text-gray-500">
      {{ t(projectId ? 'page.scenarioKits.projectHint' : 'page.scenarioKits.labHint') }}
    </p>
    <n-alert v-if="error && !showPreview" type="error">
      {{ error }} <n-button text @click="load">
        {{ t('common.retry') }}
      </n-button>
    </n-alert>
    <n-alert v-if="receipt" type="success">
      {{ t('page.scenarioKits.saved') }} <span class="break-all">{{ receipt }}</span>
    </n-alert>
    <n-spin :show="loading">
      <div class="grid gap-4 lg:grid-cols-2">
        <n-card v-for="{ kit, versions } in entries" :key="kit.id" :title="label(kit.name)" size="small">
          <div class="space-y-3">
            <p>{{ label(kit.description) }}</p>
            <p class="text-sm text-gray-500">
              {{ t('page.scenarioKits.bundled') }} · {{ kit.license }}
            </p>
            <p>{{ t('page.scenarioKits.status') }}: {{ t((projectId ? kit.application?.enabled : kit.installation?.enabled) ? 'page.scenarioKits.active' : 'page.scenarioKits.inactive') }} <span v-if="projectId ? kit.application : kit.installation">v{{ projectId ? kit.application?.version : kit.installation?.version }}</span></p>
            <n-select :aria-label="t('page.scenarioKits.version')" :value="kit.version" :options="versions.map(item => ({ label: `v${item.version}`, value: item.version }))" @update:value="selectedVersions[kit.id] = $event" />
            <p class="text-sm">
              {{ t('page.scenarioKits.modules') }}: {{ kit.modules.map(item => `${item.id} v${item.version}`).join(', ') }}
            </p>
            <n-alert v-for="item in kit.unavailable_reasons" :key="item" type="warning">
              {{ reason(item) }}
            </n-alert>
            <p v-if="projectId && !kit.installation?.enabled" class="text-sm">
              {{ t('page.scenarioKits.enableLabFirst') }}
            </p>
            <div v-if="directory?.can_manage" class="flex flex-wrap gap-2">
              <n-button type="primary" :loading="busy" :disabled="kit.unavailable_reasons.length > 0 || (Boolean(projectId) && (!kit.installation?.enabled || kit.installation.version !== kit.version))" @click="prepare(kit, projectId ? 'apply' : 'enable')">
                {{ t(projectId ? 'page.scenarioKits.apply' : 'page.scenarioKits.enable') }}
              </n-button>
              <n-button v-if="projectId ? kit.application?.enabled : kit.installation?.enabled" :disabled="busy" @click="prepare(kit, projectId ? 'deactivate' : 'disable')">
                {{ t('page.scenarioKits.deactivate') }}
              </n-button>
            </div>
          </div>
        </n-card>
      </div>
    </n-spin>
    <template v-if="directory?.can_manage">
      <n-radio-group v-if="projectId" v-model:value="strategy" :aria-label="t('page.scenarioKits.upgradeStrategy')">
        <n-space wrap>
          <n-radio value="keep">
            {{ t('page.scenarioKits.keep') }}
          </n-radio><n-radio value="new_copy">
            {{ t('page.scenarioKits.newCopy') }}
          </n-radio>
        </n-space>
      </n-radio-group>
      <p class="text-sm text-gray-500">
        {{ t('page.scenarioKits.preserveHint') }}
      </p>
      <n-button secondary @click="exportHistory">
        {{ t('page.scenarioKits.history') }}
      </n-button>
    </template>
    <n-modal v-model:show="showPreview" preset="card" :title="t('page.scenarioKits.preview')" class="max-w-[640px] w-[calc(100vw-32px)]" :mask-closable="!busy" :closable="!busy">
      <div v-if="preview" class="max-h-[65vh] overflow-auto space-y-4">
        <n-alert v-if="error" type="error">
          {{ error }}
        </n-alert>
        <p>{{ preview.destination.lab }} <span v-if="preview.destination.project">/ {{ preview.destination.project }}</span></p>
        <p>{{ label(preview.manifest.name) }} · v{{ preview.manifest.version }}</p>
        <p>{{ t(`page.scenarioKits.operations.${operation?.action}`) }}</p>
        <p>{{ t('page.scenarioKits.willCreate') }}: {{ preview.create_components.map(item => t(`page.scenarioKits.components.${item}`)).join(', ') || t('page.scenarioKits.none') }}</p>
        <p>{{ t('page.scenarioKits.existingCount', { count: preview.assets.length }) }}</p>
        <p v-for="asset in preview.assets" :key="asset.protocol_version_id">
          {{ asset.name || asset.protocol_id }} · v{{ asset.latest_version || asset.version }} <n-tag v-if="asset.changed" type="warning">
            {{ t('page.scenarioKits.customized') }}
          </n-tag>
        </p>
        <p>{{ t('page.scenarioKits.preserveHint') }}</p>
        <n-alert v-for="item in preview.blockers" :key="item" type="warning">
          {{ reason(item) }}
        </n-alert>
        <div class="flex justify-end gap-3">
          <n-button :disabled="busy" @click="showPreview = false">
            {{ t('common.cancel') }}
          </n-button><n-button type="primary" :loading="busy" :disabled="preview.blockers.length > 0" @click="confirm">
            {{ t('common.confirm') }}
          </n-button>
        </div>
      </div>
    </n-modal>
  </section>
</template>
