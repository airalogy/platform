<script setup lang="ts">
import type { InstrumentGateway } from "@/service/api/research-instruments"
import { fetchInstrumentEquipment } from "@/service/api/research-instruments"
import { $t } from "@airalogy/shared/locales"
import InstrumentAuthoringPanel from "./instrument-authoring-panel.vue"
import InstrumentExplorationPanel from "./instrument-exploration-panel.vue"
import InstrumentInstallationsPanel from "./instrument-installations-panel.vue"
import InstrumentIntegrationPanel from "./instrument-integration-panel.vue"
import InstrumentPackagesPanel from "./instrument-packages-panel.vue"
import InstrumentPairingPanel from "./instrument-pairing-panel.vue"
import InstrumentSurveyPanel from "./instrument-survey-panel.vue"

const props = defineProps<{ labId: string, gateway: InstrumentGateway }>()
const emit = defineEmits<{ updated: [] }>()
const route = useRoute()
const router = useRouter()
const steps = ["connect", "prepare", "install", "use"] as const
const tools = ["reuse", "survey", "author", "explore", "rehearse"] as const
type Step = typeof steps[number]
type Tool = typeof tools[number]
interface Option { label: string, value: string }
const initial = route.query.instrument_gateway === props.gateway.id
const step = ref<Step>(initial && steps.includes(route.query.instrument_step as Step) ? route.query.instrument_step as Step : "connect")
const tool = ref<Tool>(initial && tools.includes(route.query.instrument_tool as Tool) ? route.query.instrument_tool as Tool : "reuse")
const resourceId = ref("")
const chosen = ref<Option | null>(null)
const options = ref<Option[]>([])
const scopedOptions = computed(() => chosen.value ? [chosen.value] : [])
const search = ref("")
const busy = ref(false)
const contextReady = ref(false)
const failed = ref(false)
const unavailable = ref(false)
const more = ref(false)
const offset = ref(0)
const visited = ref(step.value !== "connect" && (step.value !== "prepare" || tool.value !== "reuse"))
let generation = 0
let timer: ReturnType<typeof setTimeout> | undefined
const initialResource = initial && typeof route.query.instrument_resource === "string" ? route.query.instrument_resource : ""
let allowAutoSelect = !initialResource
const visitedTools = reactive(new Set<Tool>([tool.value]))

function remember() {
  // Navigation only; no credentials, forms, permissions or completion state.
  void router.replace({ path: route.path, query: { ...route.query, instrument_gateway: props.gateway.id, instrument_resource: resourceId.value || undefined, instrument_step: step.value, instrument_tool: tool.value } })
}
watch([step, tool], () => {
  visitedTools.add(tool.value)
  if (step.value === "install" || step.value === "use" || (step.value === "prepare" && tool.value !== "reuse"))
    visited.value = true
  remember()
})
function confirmLeave() {
  if (!visited.value)
    return Promise.resolve(true)
  return new Promise<boolean>((resolve) => {
    if (!window.$dialog) {
      resolve(false)
      return
    }
    window.$dialog.warning({
      title: $t("page.instrumentOnboarding.changeTitle"),
      content: $t("page.instrumentOnboarding.changeHint"),
      positiveText: $t("common.confirm"),
      negativeText: $t("common.cancel"),
      onPositiveClick: () => resolve(true),
      onNegativeClick: () => resolve(false),
      onClose: () => resolve(false),
      onMaskClick: () => resolve(false),
    })
  })
}
defineExpose({ confirmLeave, equipmentOptions: scopedOptions })
async function choose(value: string | null) {
  if ((value || "") === resourceId.value || !await confirmLeave())
    return
  generation++
  clearTimeout(timer)
  busy.value = false
  allowAutoSelect = false
  chosen.value = options.value.find(item => item.value === value) || null
  resourceId.value = chosen.value?.value || ""
  unavailable.value = false
  visited.value = step.value !== "connect" && (step.value !== "prepare" || tool.value !== "reuse")
  remember()
}
async function load(append = false, selectedId?: string) {
  const current = ++generation
  busy.value = true
  failed.value = false
  const query = search.value
  try {
    const response = await fetchInstrumentEquipment(props.gateway.id, { q: query || undefined, offset: append ? offset.value : 0 })
    const validId = selectedId && /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(selectedId)
    const selected = validId ? await fetchInstrumentEquipment(props.gateway.id, { resource_id: selectedId }) : null
    if (current !== generation)
      return
    const list = response.items.map(item => ({ label: `${item.name} · ${item.code}`, value: item.id }))
    options.value = [...new Map((append ? [...options.value, ...list] : list).map(item => [item.value, item])).values()]
    more.value = response.has_more
    offset.value = response.next_offset
    if (selectedId) {
      const item = selected?.items.find(item => item.id === selectedId)
      chosen.value = item ? { value: item.id, label: `${item.name} · ${item.code}` } : null
      resourceId.value = chosen.value?.value || ""
      unavailable.value = !chosen.value
    }
    else if (allowAutoSelect && !resourceId.value && !unavailable.value && !query && !append && !response.has_more && options.value.length === 1) {
      chosen.value = options.value[0]
      resourceId.value = chosen.value.value
    }
    allowAutoSelect = false
    if (chosen.value && !options.value.some(item => item.value === chosen.value!.value))
      options.value.unshift(chosen.value)
    // Resolve restored context before mounting history/tools. Otherwise an
    // unscoped history can open a dialog that the late selection then destroys.
    contextReady.value = true
    remember()
  }
  catch {
    if (current === generation)
      failed.value = true
  }
  finally {
    if (current === generation)
      busy.value = false
  }
}
function find(value: string) {
  search.value = value
  clearTimeout(timer)
  // Invalidate in-flight responses immediately, not after the debounce.
  generation++
  timer = setTimeout(() => load(), 250)
}
onMounted(() => load(false, initialResource || undefined))
onBeforeUnmount(() => {
  generation++
  clearTimeout(timer)
})
</script>

<template>
  <section class="onboarding" data-testid="instrument-onboarding">
    <header>
      <h3>{{ $t("page.instrumentOnboarding.title") }}</h3>
      <p>{{ $t("page.instrumentOnboarding.hint") }}</p>
    </header>
    <div class="onboarding-context">
      <div class="min-w-0 flex-1">
        <label id="onboarding-equipment-label">{{ $t("page.resourceLibrary.equipment") }}</label>
        <n-select :value="resourceId || null" :options="options" :loading="busy" :disabled="!contextReady" filterable remote clearable aria-labelledby="onboarding-equipment-label" data-testid="onboarding-equipment" :placeholder="$t('page.instrumentOnboarding.selectEquipment')" @search="find" @update:value="choose" />
      </div>
      <n-button :loading="busy" @click="search = ''; load(false, (contextReady ? resourceId : initialResource) || undefined)">
        {{ $t("common.refresh") }}
      </n-button>
      <n-button v-if="more" :loading="busy" @click="load(true)">
        {{ $t("page.resourceLibrary.installMore") }}
      </n-button>
    </div>
    <operation-feedback v-if="failed" />
    <n-alert v-if="unavailable" type="warning">
      {{ $t("page.instrumentOnboarding.unavailable") }}
    </n-alert>
    <p class="onboarding-boundary">
      {{ $t("page.instrumentOnboarding.boundary") }}
    </p>
    <n-tabs v-if="contextReady" v-model:value="step" type="line" animated data-testid="onboarding-steps">
      <n-tab-pane name="connect" :tab="$t('page.instrumentOnboarding.steps.connect')" display-directive="show:lazy">
        <p>{{ $t("page.instrumentOnboarding.connectHint") }}</p>
        <instrument-pairing-panel :gateway="gateway" @updated="emit('updated')" />
      </n-tab-pane>
      <n-tab-pane name="prepare" :tab="$t('page.instrumentOnboarding.steps.prepare')" display-directive="show:lazy">
        <p>{{ $t("page.instrumentOnboarding.prepareHint") }}</p>
        <n-select v-model:value="tool" class="my-3" :options="tools.map(value => ({ value, label: $t(`page.instrumentOnboarding.tools.${value}`) }))" data-testid="onboarding-tool" />
        <instrument-packages-panel v-show="tool === 'reuse'" :lab-id="labId" />
        <div v-if="resourceId" :key="resourceId">
          <instrument-survey-panel v-if="visitedTools.has('survey')" v-show="tool === 'survey'" :gateway-id="gateway.id" :equipment-options="scopedOptions" />
          <instrument-authoring-panel v-if="visitedTools.has('author')" v-show="tool === 'author'" :gateway-id="gateway.id" :equipment-options="scopedOptions" />
          <instrument-exploration-panel v-if="visitedTools.has('explore')" v-show="tool === 'explore'" :gateway-id="gateway.id" :equipment-options="scopedOptions" />
          <instrument-integration-panel v-if="visitedTools.has('rehearse')" v-show="tool === 'rehearse'" :gateway-id="gateway.id" :gateway-name="gateway.name" :equipment-options="scopedOptions" :resource-id="resourceId" />
        </div>
        <n-empty v-else-if="tool !== 'reuse'" :description="$t('page.instrumentOnboarding.selectEquipment')" class="py-8" />
      </n-tab-pane>
      <n-tab-pane name="install" :tab="$t('page.instrumentOnboarding.steps.install')" display-directive="show:lazy">
        <p>{{ $t("page.instrumentOnboarding.installHint") }}</p>
        <p v-if="!resourceId">
          {{ $t("page.instrumentOnboarding.allHistory") }}
        </p>
        <instrument-installations-panel :key="resourceId" :lab-id="labId" :gateway-id="gateway.id" :equipment-options="scopedOptions" :resource-id="resourceId || undefined" :require-equipment="true" />
      </n-tab-pane>
      <n-tab-pane name="use" :tab="$t('page.instrumentOnboarding.steps.use')" display-directive="show:lazy">
        <p>{{ $t("page.instrumentOnboarding.useHint") }}</p>
        <slot v-if="resourceId" name="commands" :resource-id="resourceId" :equipment-options="scopedOptions" />
        <n-empty v-else :description="$t('page.instrumentOnboarding.selectEquipment')" class="py-8" />
      </n-tab-pane>
    </n-tabs>
  </section>
</template>

<style scoped>
.onboarding { min-width: 0; border: 1px solid #e7ebf2; border-radius: 12px; padding: 20px; }
.onboarding header h3 { margin: 0; }
.onboarding p { margin: 8px 0 16px; overflow-wrap: anywhere; }
.onboarding-context { display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-end; }
.onboarding-context label { display: block; margin-bottom: 6px; }
.onboarding-boundary { color: #657086; font-size: 13px; }
@media (max-width: 600px) { .onboarding { padding: 12px; } .onboarding-context > div { flex-basis: 100%; } }
</style>
