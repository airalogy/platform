<script setup lang="ts">
import type { ResourceItem } from "@/service/api/resources"
import type { KitAsset, KitDirectory } from "@/service/api/scenario-kits"
import { fetchResources } from "@/service/api/resources"
import { downloadKitFile, fetchSampleTemplate, registerKitSample } from "@/service/api/scenario-kits"
import { computed, ref, watch } from "vue"
import { useI18n } from "vue-i18n"
import { useRoute } from "vue-router"
import { useProjectInfoStore } from "../project-protocols/hooks/useProjectInfoStore"
import BulkImportRecordsModal from "../project-protocols/modules/bulk-import-records-modal.vue"
import KitCatalog from "./kit-catalog.vue"

const { projectInfo } = useProjectInfoStore()
const { t, locale } = useI18n()
const route = useRoute()
const directory = ref<KitDirectory>()
const selectedKit = ref("")
const selectedProtocol = ref("")
const samples = ref<ResourceItem[]>([])
const selectedSamples = ref<string[]>([])
const q = ref("")
const page = ref(1)
const loadingSamples = ref(false)
const busy = ref(false)
const error = ref("")
const success = ref("")
const showSample = ref(false)
const values = ref({ name: "", code: "", category: "", source: "", storage: "" })
const activeKits = computed(() => (directory.value?.kits || []).filter(kit => kit.application?.enabled && kit.version === kit.application.version && kit.installation?.enabled && !kit.unavailable_reasons.length))
const activeKit = computed(() => activeKits.value.find(kit => kit.id === selectedKit.value))
const assets = computed(() => activeKit.value?.application?.assets.filter(asset => asset.available) || [])
const asset = computed(() => assets.value.find(item => item.protocol_id === selectedProtocol.value))
const kitOptions = computed(() => activeKits.value.map(kit => ({ label: kit.name[locale.value] || kit.name[locale.value.startsWith("zh") ? "zh-CN" : "en-US"], value: kit.id })))
const protocolOptions = computed(() => assets.value.map(item => ({ label: `${item.name} · v${item.latest_version}`, value: item.protocol_id })))
let sequence = 0
function protocolRoute(name: "add-protocol-record" | "protocol-detail" | "protocol-records", item: KitAsset) {
  return { name, params: { labUid: route.params.labUid, projectUid: route.params.projectUid, protocolUid: item.uid } }
}
function errorText(err: unknown) {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return typeof detail === "string" ? detail : err instanceof Error ? err.message : t("page.scenarioKits.failed")
}
async function loadSamples() {
  const current = ++sequence
  selectedSamples.value = []
  samples.value = []
  if (!projectInfo.value || !asset.value)
    return
  loadingSamples.value = true
  error.value = ""
  try {
    const result = await fetchResources(projectInfo.value.lab_id, { resource_type_id: asset.value.resource_type_id, q: q.value || undefined, status: "active", page: page.value, page_size: 20 })
    if (current === sequence)
      samples.value = result.items
  }
  catch (err) {
    if (current === sequence)
      error.value = errorText(err)
  }
  finally {
    if (current === sequence)
      loadingSamples.value = false
  }
}
async function saveSample() {
  if (!projectInfo.value || !activeKit.value)
    return
  busy.value = true
  error.value = ""
  try {
    await registerKitSample(projectInfo.value.lab_id, projectInfo.value.id, { kit_id: activeKit.value.id, ...values.value })
    showSample.value = false
    success.value = t("page.scenarioKits.sampleSaved")
    values.value = { name: "", code: "", category: "", source: "", storage: "" }
    q.value = ""
    page.value = 1
    await loadSamples()
  }
  catch (err) { error.value = errorText(err) }
  finally { busy.value = false }
}
async function downloadTemplate() {
  if (!projectInfo.value || !activeKit.value || !asset.value)
    return
  busy.value = true
  error.value = ""
  try {
    const result = await fetchSampleTemplate(projectInfo.value.lab_id, projectInfo.value.id, { kit_id: activeKit.value.id, protocol_id: asset.value.protocol_id, sample_ids: selectedSamples.value })
    downloadKitFile(result.csv, `sample-results-v${result.protocol_version}.csv`)
  }
  catch (err) { error.value = errorText(err) }
  finally { busy.value = false }
}
watch(() => projectInfo.value?.id, () => {
  directory.value = undefined
  samples.value = []
  selectedSamples.value = []
  showSample.value = false
  success.value = ""
  error.value = ""
})
watch(activeKits, (items) => {
  if (!items.some(item => item.id === selectedKit.value))
    selectedKit.value = items[0]?.id || ""
})
watch(assets, (items) => {
  if (!items.some(item => item.protocol_id === selectedProtocol.value))
    selectedProtocol.value = items.at(-1)?.protocol_id || ""
})
watch(() => [projectInfo.value?.id, asset.value?.protocol_id], () => {
  page.value = 1
  void loadSamples()
})
watch(page, () => void loadSamples())
</script>

<template>
  <div v-if="projectInfo" class="min-w-0 space-y-6" data-testid="scenario-workbench">
    <header class="space-y-2">
      <h1 class="aira-type-page-title">
        {{ t('page.scenarioKits.workbench') }}
      </h1><p>{{ t('page.scenarioKits.workflowHint') }}</p>
    </header>
    <n-alert v-if="error && !showSample" type="error">
      {{ error }}
    </n-alert>
    <n-alert v-if="success" type="success" closable @close="success = ''">
      {{ success }}
    </n-alert>
    <template v-if="activeKits.length">
      <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <n-select v-model:value="selectedKit" :options="kitOptions" :aria-label="t('page.scenarioKits.title')" /><n-select v-model:value="selectedProtocol" :options="protocolOptions" :aria-label="t('page.scenarioKits.protocol')" />
      </div>
      <n-alert v-if="!assets.length" type="warning">
        {{ t('page.scenarioKits.noAccessibleProtocol') }}
      </n-alert>
      <template v-if="asset">
        <n-card :title="t('page.scenarioKits.samples')" size="small">
          <div class="space-y-4">
            <p class="text-sm text-gray-500">
              {{ t('page.scenarioKits.sharedSamples') }}
            </p>
            <router-link :to="{ name: 'lab-resources', params: { labUid: route.params.labUid, section: 'resources' } }">
              <n-button secondary>
                {{ t('page.resourceLibrary.title') }}
              </n-button>
            </router-link>
            <div class="flex flex-wrap gap-2">
              <n-input v-model:value="q" :placeholder="t('page.scenarioKits.searchSamples')" :input-props="{ 'aria-label': t('page.scenarioKits.searchSamples') }" class="max-w-full !w-64" @keyup.enter="page = 1; loadSamples()" /><n-button @click="page = 1; loadSamples()">
                {{ t('common.search') }}
              </n-button><n-button v-if="directory?.can_register_samples" type="primary" @click="showSample = true">
                {{ t('page.scenarioKits.registerSample') }}
              </n-button>
            </div>
            <n-spin :show="loadingSamples">
              <n-empty v-if="!samples.length" :description="t('page.scenarioKits.noSamples')" /><n-checkbox-group v-else v-model:value="selectedSamples">
                <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <label v-for="sample in samples" :key="sample.id" class="flex items-start gap-3 border rounded p-3"><n-checkbox :value="sample.id" :aria-label="sample.code" /><span class="min-w-0 break-words">{{ sample.name }}<span class="block text-sm text-gray-500">{{ sample.code }}</span></span></label>
                </div>
              </n-checkbox-group>
            </n-spin>
            <div class="flex flex-wrap items-center gap-2">
              <n-button :disabled="page === 1 || loadingSamples" @click="page--">
                {{ t('page.scenarioKits.previous') }}
              </n-button><span>{{ page }}</span><n-button :disabled="samples.length < 20 || loadingSamples" @click="page++">
                {{ t('page.scenarioKits.next') }}
              </n-button>
            </div>
            <n-button v-if="asset.can_record" class="sample-template-action" :disabled="!selectedSamples.length" :loading="busy" @click="downloadTemplate">
              {{ t('page.scenarioKits.sampleTemplate', { count: selectedSamples.length }) }}
            </n-button>
            <p class="text-sm text-gray-500">
              {{ t('page.scenarioKits.templateHint') }}
            </p>
          </div>
        </n-card>
        <div class="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <n-card :title="t('page.scenarioKits.record')" size="small">
            <div class="space-y-3">
              <p>{{ t('page.scenarioKits.recordHint') }}</p><div class="flex flex-wrap gap-2">
                <router-link v-if="asset.can_record" :to="protocolRoute('add-protocol-record', asset)">
                  <n-button type="primary">
                    {{ t('page.scenarioKits.record') }}
                  </n-button>
                </router-link><router-link :to="protocolRoute('protocol-detail', asset)">
                  <n-button>{{ t('page.scenarioKits.protocol') }}</n-button>
                </router-link>
              </div>
            </div>
          </n-card>
          <n-card :title="t('page.scenarioKits.import')" size="small">
            <div class="space-y-3">
              <p>{{ t('page.scenarioKits.importHint') }}</p><bulk-import-records-modal v-if="asset.can_record" :protocol-id="asset.protocol_id" @imported="success = t('page.scenarioKits.imported')" /><router-link v-if="asset.can_read_records" :to="protocolRoute('protocol-records', asset)" class="block">
                <n-button>{{ t('page.scenarioKits.records') }}</n-button>
              </router-link>
            </div>
          </n-card>
          <n-card :title="t('page.scenarioKits.analyze')" size="small">
            <div class="space-y-3">
              <p>{{ t('page.scenarioKits.analysisHint') }}</p><router-link v-if="asset.can_read_records" :to="{ name: 'project-analysis', params: { labUid: route.params.labUid, projectUid: route.params.projectUid }, query: { protocolId: asset.protocol_id, scenarioKit: activeKit?.id } }">
                <n-button type="primary">
                  {{ t('page.scenarioKits.analyze') }}
                </n-button>
              </router-link>
            </div>
          </n-card>
        </div>
      </template>
    </template>
    <n-alert v-else type="info">
      {{ t('page.scenarioKits.emptyHint') }}
    </n-alert>
    <kit-catalog :lab-id="projectInfo.lab_id" :project-id="projectInfo.id" @changed="directory = $event" />
    <n-modal v-model:show="showSample" preset="card" :content-style="{ maxHeight: '65vh', overflowY: 'auto' }" :title="t('page.scenarioKits.registerSample')" class="max-w-[560px] w-[calc(100vw-32px)]" :mask-closable="!busy" :closable="!busy">
      <n-alert v-if="error" type="error" class="mb-4">
        {{ error }}
      </n-alert>
      <n-form label-placement="top" @submit.prevent="saveSample">
        <n-form-item v-for="field in (['name', 'code', 'category', 'source', 'storage'] as const)" :key="field" :label="t(`page.scenarioKits.fields.${field}`)" :required="['name', 'code', 'category'].includes(field)">
          <n-input v-model:value="values[field]" :input-props="{ 'aria-label': t(`page.scenarioKits.fields.${field}`), 'required': ['name', 'code', 'category'].includes(field) }" :maxlength="field === 'name' ? 255 : ['source', 'storage'].includes(field) ? 1000 : 128" />
        </n-form-item>
        <p class="mb-4 text-sm">
          {{ t('page.scenarioKits.saveLocation', { lab: directory?.lab_name }) }}
        </p>
        <div class="flex justify-end gap-2">
          <n-button :disabled="busy" @click="showSample = false">
            {{ t('common.cancel') }}
          </n-button><n-button type="primary" attr-type="submit" :loading="busy" :disabled="!values.name.trim() || !values.code.trim() || !values.category.trim()">
            {{ t('common.save') }}
          </n-button>
        </div>
      </n-form>
    </n-modal>
  </div>
</template>

<style scoped>
.sample-template-action {
  max-width: 100%;
  height: auto;
  min-height: 34px;
  padding-block: 8px;
}

.sample-template-action :deep(.n-button__content) {
  white-space: normal;
  line-height: 1.5;
}
</style>
