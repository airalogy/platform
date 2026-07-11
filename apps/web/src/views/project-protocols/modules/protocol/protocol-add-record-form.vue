<template>
  <add-record-layout
    v-if="fieldRecordDefault"
    v-model:collapsed="isCollapsed"
    v-model:split-size="splitSize"
    v-model:selected-tab="selectedTab"
    :dom-mounted="domMounted"
    :default-spilt-size="props.defaultSpiltSize"
  >
    <template #tabs>
      <n-tab-pane
        name="ai-assistant" class="relative" :tab="$t('chat.askAira')"
        display-directive="show"
        :style="{ paddingLeft: isCollapsed ? '32px' : undefined }"
      >
        <template #tab>
          <ai-menu-icon
            outlined :selected="selectedTab === 'ai-assistant'" data-tab="ai-assistant"
            @click="handleCollapse"
          />
        </template>
        <div class="h-full pl-4" :class="{ hidden: isCollapsed }">
          <div class="mb-2 h-10 w-fit rounded bg-[#2B2B38] px-4 text-[1.125rem] text-white leading-10">
            {{ $t("chat.askAira") }}
          </div>
          <chat-component
            ref="chatRef"
            v-model:docked="docked"
            v-model:full-screen="appStore.fullContent"
            v-model:role="role"
            v-model:could-change-role="couldChangeRole"
            hide-collapse
            :collapsed="isCollapsed"
            :class="appStore.fullContent ? 'h-screen' : 'h-[calc(100%-3rem)]'"
            :protocol-id="props.protocolId"
            source="protocol" enable-tool-action :airalogy-id="airalogyId"
            :resolve-file="getCachedAttachment"
            @update:docked="handleUpdateDocked"
          />
        </div>
      </n-tab-pane>
      <n-tab-pane
        name="form-fields" class="relative" :tab="$t('common.fields')"
        display-directive="show"
        :style="{ paddingLeft: isCollapsed ? '32px' : undefined }"
      >
        <template #tab>
          <field-form-icon
            :selected="selectedTab === 'form-fields'" data-tab="form-fields"
            @click="handleCollapse"
          />
        </template>
        <div class="px-4" :class="{ hidden: isCollapsed }">
          <div class="mb-2 h-10 w-fit rounded bg-[#2B2B38] px-4 text-[1.125rem] text-white leading-10">
            {{ $t("common.fields") }}
          </div>

          <!-- Field Input Bar -->
          <div class="mb-4">
            <field-input-bar :protocol-id="props.protocolId" />
          </div>
        </div>

        <n-collapse
          v-model:expanded-names="expandedNamesRef" display-directive="show"
          class="px-4"
          :class="{ hidden: isCollapsed }"
        >
          <n-form ref="formRef" class="h-full pb-3" :rules="fieldRecordDefault.rules" :model="fieldModel">
            <n-collapse-item v-for="(scopeName, idx) in scopeList" :key="scopeName" :name="scopeName">
              <template #header>
                <span class="text-4 font-500 capitalize">
                  {{ fieldRecordDefault.field[scopeName]?.__SCOPE__?.title || scopeKeyRecord[scopeName] }}
                </span>
              </template>
              <template #header-extra>
                <n-tag :color="getTagColor(scopeName)">
                  <n-ellipsis>
                    {{ scopeKeyRecord[scopeName] }}
                  </n-ellipsis>
                </n-tag>
              </template>
              <template v-for="(prop, index) in fieldPropList[idx]" :key="prop">
                <protocol-add-record-form-item
                  v-bind="createFormItemProps(scopeName, prop)"
                  :should-scroll="shouldScroll"
                  @field:change="handleFieldChange"
                />
                <n-divider v-if="index !== fieldPropList[idx].length - 1" class="!mb-4 !mt-0" />
              </template>
            </n-collapse-item>
          </n-form>
        </n-collapse>
      </n-tab-pane>
      <n-tab-pane
        v-if="hasWorkflowScope"
        name="workflow"
        class="relative"
        :tab="$t('page.protocol.workflow.workspaceTab')"
        display-directive="show"
        :style="{ paddingLeft: isCollapsed ? '32px' : undefined }"
      >
        <template #tab>
          <n-icon
            :size="24"
            class="mx-auto cursor-pointer rounded-lg p-2 transition-colors"
            :class="selectedTab === 'workflow' ? 'bg-primary/10 text-primary' : 'text-gray-500 hover:bg-gray-100'"
            data-tab="workflow"
            @click="handleCollapse"
          >
            <icon-tabler-git-branch />
          </n-icon>
        </template>

        <div class="px-4" :class="{ hidden: isCollapsed }">
          <div class="mb-2 h-10 w-fit rounded bg-[#2B2B38] px-4 text-[1.125rem] text-white leading-10">
            {{ $t("page.protocol.workflow.workspaceTab") }}
          </div>
          <n-text depth="3">
            {{ $t("page.protocol.workflow.workspaceTabDescription") }}
          </n-text>
        </div>
      </n-tab-pane>
    </template>
    <template #content>
      <slot name="prefix" />
      <workflow-workspace
        v-if="selectedTab === 'workflow' && hasWorkflowScope"
        :workflow-id="workflowId"
        :readonly="props.readonly"
      />
      <n-form
        v-else-if="fieldRecordDefault"
        class="platform-aimd-form-preview"
        :rules="previewFormRecord?.rules"
        :model="previewValue"
      >
        <aimd-markdown-preview
          ref="previewRef"
          :content="templateRef"
          :mode="previewMode"
          :value="previewValue"
          class="px-6"
          :render-options="previewAimdRenderOptions"
          :readonly-record-data="readonlyRecordData"
          :mermaid-component="MermaidBlock"
          :resolve-url="resolvePreviewFile"
          body-class="markdown-body"
          @render:result="handlePreviewRendered"
        />
        <protocol-bubble-menu
          v-if="previewRef?.rootElement"
          :container-ref="previewRef.rootElement"
        />
      </n-form>
    </template>
  </add-record-layout>
  <!-- <asset-aimd v-if="domMounted && props.protocol" :uuid="props.protocol.id" /> -->

  <!-- Assigner Progress Modal -->
  <assigner-progress-modal
    :state="assignerProgressModalState"
    @close="handleAssignerProgressClose"
    @toggle-detail="handleToggleDetail"
  />
</template>

<script setup lang="ts">
import type { IEmits as AIMDEmits, IAIMDWrapperProps } from "@/components/custom/aimd/types/aimd-types"
import type { AimdTemplateEnv, IRecordData, IRecordDataKey, ScopeFieldKey } from "@airalogy/aimd-core/types"
import type { ContextItemWithId } from "@airalogy/components/chat/providers/types"
import type { CurrentRecorderRecordFieldSummary } from "@airalogy/components/chat/providers/useChatProvider"

import type { ResolveContextItemPayload } from "@airalogy/components/chat/utils/resolveInput"
import type { AddToChatPayload, BubbleMenuEventName, BubbleMenuEventPayload } from "@airalogy/composables/useBubbleMenu"

import type { ProtocolModels } from "@airalogy/shared"
import type { FormValidate } from "naive-ui/es/form/src/interface"
import type { TagColor } from "naive-ui/es/tag/src/common-props"

import type { IFieldChangePayload } from "./types/types"
import ChatComponent from "@/components/chat/index.vue"
import AddRecordLayout from "@/components/custom/add-record-layout.vue"
import { createPlatformAimdFormRenderers } from "@/components/custom/aimd/composables/createPlatformAimdFormRenderers"
import { useAIMDProvide } from "@/components/custom/aimd/composables/useAIMDHelpers"
import { useNaiveForm } from "@/composables"

import { getCachedAttachment } from "@/service/api/attachments"
import { useAppStore } from "@/store/modules/app"
import { useAuthStore } from "@/store/modules/auth"
import { themeSettings } from "@/theme/settings"
import { resolveProtocolFile as resolveProtocolFileUtil } from "@/utils/resolveProtocolFile"
import { bubbleMenuEventKey, fieldEventKey } from "@/utils/template/eventKey"
import { AimdMarkdownPreview } from "@airalogy/aimd-renderer/vue"
import { useChatProvider } from "@airalogy/components/chat/providers/useChatProvider"
import MermaidBlock from "@airalogy/components/markdown-editor/modules/mermaid/mermaid-block.vue"
import ProtocolBubbleMenu from "@airalogy/components/protocol-bubble-menu.vue"
import { useClosableMessage } from "@airalogy/composables"
import { $t } from "@airalogy/shared/locales"
import { scopeKeyRecord } from "@airalogy/shared/utils/schema"
import { useEventBus } from "@vueuse/core"
import Big from "big.js"
import { cloneDeepWith as _cloneDeepWith, get as _get } from "lodash-es"
import { nanoid } from "nanoid"
import { useProtocolInfoStore } from "../../hooks/useProtocolInfoStore"
import AssignerProgressModal from "./components/AssignerProgressModal.vue"
import FieldInputBar from "./components/field-input-bar.vue"
import WorkflowWorkspace from "./components/workflow-workspace.vue"

import { useAssignerManagement } from "./composables/useAssignerManagement"
import { getAssignerProgress } from "./composables/useAssignerProgress"
import { useFieldEventBus } from "./composables/useFieldEventBus"
import { useFieldManagement } from "./composables/useFieldManagement"
import { useFieldParser } from "./composables/useFieldParser"
import { useFieldState } from "./composables/useFieldState"
import { useTableManagement } from "./composables/useTableManagement"
import ProtocolAddRecordFormItem, { type IProps as IFormItemProps } from "./protocol-add-record-form-item.vue"

defineOptions({ name: "ProtocolAddRecordForm" })

const props = withDefaults(defineProps<IProps>(), {
  protocol: null,
  defaultSpiltSize: 0.35,
  collapsed: false,
})
const emit = defineEmits<Emits>()
interface IProps {
  protocol?: ProtocolModels.ProtocolInfo | null
  protocolId: string
  defaultSpiltSize?: number
  readonly?: boolean
  recordData?: Partial<IRecordData>
  collapsed?: boolean
}

const appStore = useAppStore()

// Assigner progress modal
const { state: assignerProgressState, hide: hideAssignerProgress, toggleDetailMode } = getAssignerProgress()
const assignerProgressModalState = computed(() => assignerProgressState as any)
function handleAssignerProgressClose() {
  hideAssignerProgress()
}
function handleToggleDetail() {
  toggleDetailMode()
}

interface Emits {
  (e: "update:field", payload: { scope: IRecordDataKey, prop: string, value: any, info?: any }): void
  (e: "update:splitSize", payload: string | number): void
  (e: "update:collapsed", payload: boolean): void
  (e: "update:type", payload: { scope: IRecordDataKey, prop: string, type: string }): void
}

// const { bool: isCollapsed, setTrue: collapse, setFalse: expand, toggle } = useBoolean(false)
const isCollapsed = useVModel(props, "collapsed")
const message = useClosableMessage()

const chatRef = ref<{ setDocked: (val: boolean) => void } | null>(null)

const { airalogyId } = useProtocolInfoStore()!
const { currentRecorderRecordContext } = useChatProvider()

// Resolve file paths for protocol assets
function resolveProtocolFile(src: string) {
  if (!props.protocolId)
    return null
  return resolveProtocolFileUtil(src, props.protocolId)
}

function resolvePreviewFile(src: string) {
  return resolveProtocolFile(src) || Promise.resolve(null)
}

const splitSize = ref(props.defaultSpiltSize)

watch(
  splitSize,
  (val) => {
    if (isCollapsed.value && val > 0) {
      isCollapsed.value = false
    }
    emit("update:splitSize", val)
  },
)

const selectedTab = ref<"form-fields" | "ai-assistant" | "workflow" | undefined>("ai-assistant")
const docked = ref(false)
function handleUpdateDocked(val: boolean) {
  if (val) {
    selectedTab.value = "form-fields"
    docked.value = true
  }
  else {
    if (!isCollapsed.value) {
      selectedTab.value = "ai-assistant"
    }
    docked.value = false
  }
}

const shouldScroll = ref(false) // Enable after fields tab is opened
const stopWatch = watch(
  selectedTab,
  (val) => {
    if (val === "form-fields") {
      shouldScroll.value = true
      stopWatch()
    }
  },
)

watch(
  isCollapsed,
  (val) => {
    if (val || selectedTab.value) {
      return
    }

    selectedTab.value = "ai-assistant"
  },
)

function handleCollapse(e: MouseEvent) {
  const target = e.currentTarget as HTMLElement
  if (!target) {
    // NOPE
    return
  }

  const { tab } = target.dataset
  if (tab === "ai-assistant" && docked.value) {
    chatRef.value?.setDocked(false)
  }

  if (isCollapsed.value) {
    selectedTab.value = tab as "form-fields" | "ai-assistant"

    splitSize.value = 0.35
    void nextTick(() => {
      isCollapsed.value = false
    })
  }
  else if (!tab || tab === selectedTab.value) {
    selectedTab.value = undefined

    splitSize.value = 0
    void nextTick(() => {
      isCollapsed.value = true
    })
  }
}

interface AimdMarkdownPreviewExpose {
  env: AimdTemplateEnv
  reload: () => Promise<void>
  rootElement: HTMLElement | null
}

const previewRef = ref<AimdMarkdownPreviewExpose>()
const lastParsedAimd = ref("")
const templateRef = ref<string>(props.protocol?.aimd || "")
const { formRef, validate } = useNaiveForm()

const role = ref<1 | 2>(1)
const couldChangeRole = ref<boolean>(false)

provide("chat-role", { role, couldChangeRole })

// Ref to store AIMD form item refs (will be assigned later after useAIMDProvide)
let aimdFormItemRefStore: Record<string, { value: any }> = {}

const handleAssignerValidate: FormValidate = async (callback, shouldRuleBeApplied) => {
  // Validate AIMD form items
  if (aimdFormItemRefStore && Object.keys(aimdFormItemRefStore).length > 0) {
    for (const key in aimdFormItemRefStore) {
      const formItem = aimdFormItemRefStore[key]?.value
      if (formItem && typeof formItem.validate === "function") {
        try {
          await formItem.validate()
        }
        catch (e) {
          // Continue validating other fields
        }
      }
    }
  }

  return await validate(callback, shouldRuleBeApplied)
}

function restoreValidation() {
  // Restore validation for AIMD form items
  if (aimdFormItemRefStore && Object.keys(aimdFormItemRefStore).length > 0) {
    for (const key in aimdFormItemRefStore) {
      const formItem = aimdFormItemRefStore[key]?.value
      if (formItem && typeof formItem.restoreValidation === "function") {
        formItem.restoreValidation()
      }
    }
  }

  formRef.value?.restoreValidation()
}

const {
  // Models
  fieldModel,
  fieldRecordDefault,

  // Lists
  fieldPropList,
  scopeList,

  // Records
  refRecord,
  tableRecord,
  tableEmitterRecord,
  varScopeRecord,

  // Expanded Names
  expandedNamesRef,

  // Mounted State
  domMounted,
  setDomMounted,

  // Workflow Field
  workflowField,
  workflowId,

  // Restore Field Record
  restoreFieldRecord,
} = useFieldState(props, templateRef)

const previewMode = computed(() => props.readonly ? "report" : "edit")
const previewFormRecord = computed(() => props.readonly ? null : fieldRecordDefault.value)
const previewValue = computed(() => props.readonly ? undefined : fieldModel as any)
const readonlyRecordData = computed(() => {
  if (!props.readonly) {
    return undefined
  }

  const data = (props.recordData || {}) as Record<string, unknown>
  return {
    var: data.var ?? data.research_variable ?? {},
    step: data.step ?? data.research_step ?? {},
    check: data.check ?? data.research_check ?? {},
    quiz: data.quiz ?? {},
    var_table: data.var_table ?? {},
  }
})

const RECORDER_CONTEXT_FIELD_LIMIT = 200
const RECORDER_CONTEXT_ARRAY_LIMIT = 50
const RECORDER_CONTEXT_OBJECT_KEY_LIMIT = 80
const RECORDER_CONTEXT_VALUE_DEPTH_LIMIT = 4
const RECORDER_CONTEXT_SKIP_KEYS = new Set([
  "ajv",
  "assigner",
  "assignerRecord",
  "assignedSet",
  "dependent",
  "dependentRecord",
  "disabled",
  "onUpdate",
  "raw",
  "rules",
])

function sanitizeRecorderValue(value: unknown, depth = 0): unknown {
  const rawValue = toRaw(value)

  if (rawValue === null || typeof rawValue === "undefined") {
    return rawValue
  }

  if (typeof rawValue === "string" || typeof rawValue === "number" || typeof rawValue === "boolean") {
    return rawValue
  }

  if (typeof rawValue === "bigint") {
    return rawValue.toString()
  }

  if (rawValue instanceof Big) {
    return rawValue.toString()
  }

  if (rawValue instanceof Date) {
    return rawValue.toISOString()
  }

  if (typeof File !== "undefined" && rawValue instanceof File) {
    return {
      name: rawValue.name,
      size: rawValue.size,
      type: rawValue.type,
    }
  }

  if (typeof Blob !== "undefined" && rawValue instanceof Blob) {
    return {
      size: rawValue.size,
      type: rawValue.type,
    }
  }

  if (depth >= RECORDER_CONTEXT_VALUE_DEPTH_LIMIT) {
    return "[Max depth reached]"
  }

  if (Array.isArray(rawValue)) {
    const items = rawValue
      .slice(0, RECORDER_CONTEXT_ARRAY_LIMIT)
      .map(item => sanitizeRecorderValue(item, depth + 1))

    if (rawValue.length > RECORDER_CONTEXT_ARRAY_LIMIT) {
      items.push(`[${rawValue.length - RECORDER_CONTEXT_ARRAY_LIMIT} more items omitted]`)
    }

    return items
  }

  if (typeof rawValue === "object") {
    const entries = Object.entries(rawValue as Record<string, unknown>)
      .filter(([key, item]) => !key.startsWith("_") && !RECORDER_CONTEXT_SKIP_KEYS.has(key) && typeof item !== "function")
    const result: Record<string, unknown> = {}

    entries.slice(0, RECORDER_CONTEXT_OBJECT_KEY_LIMIT).forEach(([key, item]) => {
      result[key] = sanitizeRecorderValue(item, depth + 1)
    })

    if (entries.length > RECORDER_CONTEXT_OBJECT_KEY_LIMIT) {
      result.__truncated_keys = entries.length - RECORDER_CONTEXT_OBJECT_KEY_LIMIT
    }

    return result
  }

  return String(rawValue)
}

function isRecorderValueFilled(value: unknown): boolean {
  const rawValue = toRaw(value)

  if (rawValue === null || typeof rawValue === "undefined") {
    return false
  }

  if (typeof rawValue === "string") {
    return rawValue.trim().length > 0
  }

  if (typeof rawValue === "number" || typeof rawValue === "boolean" || typeof rawValue === "bigint") {
    return true
  }

  if (rawValue instanceof Big || rawValue instanceof Date) {
    return true
  }

  if (Array.isArray(rawValue)) {
    return rawValue.some(item => isRecorderValueFilled(item))
  }

  if (typeof rawValue === "object") {
    return Object.entries(rawValue as Record<string, unknown>)
      .filter(([key, item]) => !key.startsWith("_") && !RECORDER_CONTEXT_SKIP_KEYS.has(key) && typeof item !== "function")
      .some(([, item]) => isRecorderValueFilled(item))
  }

  return true
}

function getRecorderFieldSummary() {
  const fieldSummary: CurrentRecorderRecordFieldSummary[] = []
  let filledCount = 0
  let emptyCount = 0
  let truncated = false

  scopeList.value.forEach((scopeName, scopeIndex) => {
    const propList = (fieldPropList.value[scopeIndex] || []) as Array<string | [string, string[]]>

    propList.forEach((prop) => {
      const propKey = Array.isArray(prop) ? prop[0] : prop
      if (!propKey || propKey === "__SCOPE__") {
        return
      }

      const item = _get(fieldModel, [scopeName, propKey]) || _get(fieldRecordDefault.value, ["field", scopeName, propKey])
      if (!item) {
        return
      }

      const value = _get(item, "value")
      const filled = isRecorderValueFilled(value)
      if (filled) {
        filledCount += 1
      }
      else {
        emptyCount += 1
      }

      if (fieldSummary.length >= RECORDER_CONTEXT_FIELD_LIMIT) {
        truncated = true
        return
      }

      fieldSummary.push({
        scope: scopeName,
        field_id: propKey,
        title: _get(item, "title") || _get(item, "label") || propKey,
        type: _get(item, "type"),
        filled,
        ...(filled ? { value: sanitizeRecorderValue(value) } : {}),
      })
    })
  })

  return {
    emptyCount,
    fieldSummary,
    filledCount,
    truncated,
  }
}

function syncCurrentRecorderRecordContext() {
  const { emptyCount, fieldSummary, filledCount, truncated } = getRecorderFieldSummary()
  const recordData = sanitizeRecorderValue(props.recordData || {}) as Record<string, unknown>
  const enabled = fieldSummary.length > 0 || isRecorderValueFilled(recordData)

  currentRecorderRecordContext.value = enabled
    ? {
        enabled: true,
        title: props.protocol?.name || props.protocol?.uid || "Current recorder record",
        protocol_id: props.protocolId,
        protocol_uid: props.protocol?.uid,
        protocol_name: props.protocol?.name,
        readonly: Boolean(props.readonly),
        filled_count: filledCount,
        empty_count: emptyCount,
        field_summary: fieldSummary,
        record_data: recordData,
        truncated,
      }
    : { enabled: false }
}

watch(
  [fieldModel, fieldRecordDefault, fieldPropList, scopeList, () => props.protocolId, () => props.protocol?.uid, () => props.protocol?.name, () => props.recordData, () => props.readonly],
  syncCurrentRecorderRecordContext,
  { deep: true, immediate: true },
)

onBeforeUnmount(() => {
  currentRecorderRecordContext.value = { enabled: false }
})

provide("protocol-workflow", { workflowId })

const hasWorkflowScope = computed(() => scopeList.value.includes("research_workflow"))

function openWorkflowWorkspace() {
  selectedTab.value = "workflow"
  if (isCollapsed.value) {
    splitSize.value = props.defaultSpiltSize
    isCollapsed.value = false
  }
}

provide("protocol-workflow-workspace", {
  open: openWorkflowWorkspace,
})

// Create a ref to store the updateField function to resolve circular dependency
const updateFieldRef = ref<((fieldModel: any, payload: any) => Promise<void>) | null>(null)

// Create a wrapper function that calls updateField when available
async function updateFieldWrapper(fieldModel: any, payload: any) {
  if (updateFieldRef.value) {
    await updateFieldRef.value(fieldModel, payload)
  }
}

function mergeDependents(
  ...lists: Array<Array<{ name: string, scope: IRecordDataKey }> | undefined>
): Array<{ name: string, scope: IRecordDataKey }> | undefined {
  const merged = lists
    .flatMap(list => list || [])
    .filter((item): item is { name: string, scope: IRecordDataKey } => Boolean(item?.name && item?.scope))

  if (merged.length === 0) {
    return undefined
  }

  const seen = new Set<string>()
  return merged.filter((item) => {
    const key = `${item.scope}.${item.name}`
    if (seen.has(key)) {
      return false
    }
    seen.add(key)
    return true
  })
}

const { handleAssigner, handleDependent, assignerLoadingRecord, assignerErrorRecord, handleAssignerCancel, assignerRequestRecord } = useAssignerManagement({
  protocolId: props.protocolId,
  emit,
  varScopeRecord,
  validate: handleAssignerValidate,
  restoreValidation,
  shouldTrigger: !props.readonly,
  updateField: updateFieldWrapper,
})

function createFormItemProps(scopeName: string, prop: string | [string, string[]]) {
  const propKey = Array.isArray(prop) ? prop[0] : prop
  const { readonly, protocolId } = props
  const item = _get(fieldModel, [scopeName, propKey])
  const ajv = _get(fieldRecordDefault.value, ["rules", scopeName, propKey, "ajv"])

  return {
    assignerLoadingRecord,
    assignerErrorRecord,
    assignerRequestRecord,
    protocolId,
    item,
    ajv,
    propInfo: propKey,
    scope: scopeName,
    varScopeRecord,
    tableRecord,
    readonly,
  } as unknown as IFormItemProps
}

const { updateField } = useFieldManagement({ fieldModel, emit })

// Set the updateField ref to the actual updateField function
updateFieldRef.value = updateField

// Create fieldEventBus for syncing left form changes to right AIMD preview
const localFieldEventBus = useEventBus<string>(fieldEventKey)

// Wrap handleFieldChange to emit preview-field-change event for queue-based processing
// This ensures field changes go through the debounced queue mechanism
async function handleFieldChange(payload: IFieldChangePayload) {
  // Get dependent and assigner info from fieldModel
  const { scope, prop, info } = payload
  const { group } = info || {}

  let assigner = payload.assigner
  let dependent = payload.dependent

  if (group) {
    // Table field - scope is "var_table", look under research_variable
    assigner = assigner
    || _get(fieldModel, ["research_variable", group, "assignerRecord", `${group}.${prop}`])
    || _get(fieldModel, ["research_variable", group, "assignerRecord", prop])
    dependent = mergeDependents(
      dependent,
      _get(fieldModel, ["research_variable", group, "dependentRecord", `${group}.${prop}`]),
      _get(fieldModel, ["research_variable", group, "dependentRecord", prop]),
      _get(fieldModel, ["research_variable", group, "dependent"]),
    )
  }
  else {
    // Regular field
    assigner = assigner || _get(fieldModel, [scope, prop, "assigner"])
    dependent = mergeDependents(
      dependent,
      _get(fieldModel, [scope, prop, "dependent"]),
    )
  }

  // Emit preview-field-change event to go through the queue mechanism
  localFieldEventBus.emit("preview-field-change", {
    ...payload,
    assigner,
    dependent,
  })

  // Also emit form-field-change event to sync left form changes to right AIMD preview
  localFieldEventBus.emit("form-field-change", payload)
}

const { setupFieldEventHandlers } = useFieldEventBus(
  fieldModel,
  expandedNamesRef,
  handleAssigner,
  handleDependent,
  handleAssignerCancel,
  updateField,
  emit,
  varScopeRecord,
  props.protocol?.assigners,
)

const { handleTableRowUpdate } = useTableManagement()

const { handleParseField } = useFieldParser(
  fieldModel,
  props.protocol,
  scopeList,
  fieldPropList,
  refRecord,
  tableRecord as any,
  tableEmitterRecord,
)

// function handleMedia(sourceList: HTMLSourceElement[]) {
//   if (!props.protocol || !props.protocol.id) {
//     return
//   }

//   sourceList.forEach(async (source) => {
//     const src = source.getAttribute("src")
//     if (!src) {
//       return
//     }

//     try {
//       const res = await getStaticResearchAssets(props.protocol!.id, src)
//       if (res && res.data) {
//         const parent = source.parentElement

//         if (parent) {
//           source.src = res.data.url
//           // eslint-disable-next-line no-self-assign
//           parent.outerHTML = parent.outerHTML
//         }
//       }
//     }
//     catch (e) {
//       message.error((e as Error).message)
//     }
//   })
// }

// Initialize event handlers
setupFieldEventHandlers()

// Update template refs for table row updates
function handleTableRowActions(type: "add-row" | "remove-row", payload: any) {
  handleTableRowUpdate(type, payload, tableEmitterRecord, fieldModel)
}

async function wrappedValidate() {
  // Expand all collapsed sections to show validation errors
  expandedNamesRef.value = [...scopeList.value]
  await nextTick()

  let leftFormError: Error | null = null
  let rightFormError: Error | null = null

  // Validate form fields on the left side
  try {
    await validate()
  }
  catch (e) {
    leftFormError = e as Error
  }

  // Validate AIMD fields on the right side
  // aimdFormItemRefStore is a Record<string, { value: FormItemInst | null }>
  if (aimdFormItemRefStore && Object.keys(aimdFormItemRefStore).length > 0) {
    const validationPromises: Promise<any>[] = []

    for (const key in aimdFormItemRefStore) {
      const formItem = aimdFormItemRefStore[key]?.value
      if (formItem && typeof formItem.validate === "function") {
        validationPromises.push(
          formItem.validate().catch((e: Error) => {
            if (!rightFormError) {
              rightFormError = e
            }
            throw e
          }),
        )
      }
    }

    try {
      await Promise.all(validationPromises)
    }
    catch (e) {
      // Errors are already captured in rightFormError
    }
  }

  // If there are any validation errors, throw the first error to maintain original behavior
  if (leftFormError || rightFormError) {
    throw leftFormError || rightFormError
  }
}

const bubbleMenuEventBus = useEventBus<BubbleMenuEventName, BubbleMenuEventPayload>(bubbleMenuEventKey)

bubbleMenuEventBus.on((event, payload) => {
  if (event === "triggerChatAction" && typeof payload === "object") {
    const { event: eventType, value } = payload as { event: "sendToChat" | "addToChat", value: string | AddToChatPayload }
    isCollapsed.value = false
    if (!docked.value) {
      selectedTab.value = "ai-assistant"
    }

    void nextTick(() => {
      if (typeof value === "string") {
        bubbleMenuEventBus.emit(eventType, value)
      }
      else {
        const { prop, scope, type } = value as AddToChatPayload
        const modelValue = _get(fieldModel, [scope, prop, "value"])
        let formattedValue = modelValue
        if (typeof modelValue === "object") {
          if (modelValue.airalogy_file_id) {
            formattedValue = `"${modelValue.airalogy_file_id}"`
          }
          else if (modelValue.value) {
            formattedValue = modelValue.value
          }
          else {
            formattedValue = JSON.stringify(modelValue, null, 0)
          }
        }
        else if (typeof modelValue === "string") {
          formattedValue = `"${modelValue}"`
        }

        const formattedScope = scopeKeyRecord[scope as ScopeFieldKey] as IRecordDataKey
        const id = `${formattedScope}.${prop}`

        bubbleMenuEventBus.emit(eventType, {
          prop,
          scope: formattedScope,
          value: formattedValue,
          type,
          mentionAttrs: {
            id,
            label: id,
            query: id,
            // TODO: resolve context items, items may change after the mention is inserted
            renderInlineAs: `{{${formattedScope}|${prop}, value=${formattedValue || ""}, type=${type}}}`,
            itemType: "getFieldValue",
          },
        })
      }
    })
  }
})

const contextBus = useEventBus<"request:context/getContextItems" | "response:context/getContextItems", ResolveContextItemPayload | ContextItemWithId[]>("submenu-eventbus")

contextBus.on(async (event, payload) => {
  if (event !== "request:context/getContextItems" || !payload) {
    return
  }

  const { name, query } = payload as ResolveContextItemPayload

  if (!name || !query) {
    return
  }

  const [scope, prop] = query.split(".")

  if (!scope || !prop) {
    return
  }

  const result = _get(fieldModel, [scope, prop, "value"])

  const response: ContextItemWithId[] = [{
    content: result,
    id: {
      providerTitle: "",
      itemId: "",
    },
    description: "",
    name: "",
  }]

  contextBus.emit("response:context/getContextItems", response)
})

const isEditorBubbleActive = ref(false)
provideLocal("isEditorBubbleActive", isEditorBubbleActive)

function getTagColor(scopeName: string): TagColor {
  const { colors } = themeSettings.tokens.light
  switch (scopeName) {
    case "research_variable":
      return { color: colors["field-var-bg"], textColor: "white", borderColor: colors["field-var-bg"] } as TagColor
    case "var_table":
      return { color: colors["field-table-bg"], textColor: "white", borderColor: colors["field-table-bg"] } as TagColor
    case "research_check":
      return { color: colors["field-check-bg"], textColor: "white", borderColor: colors["field-check-bg"] } as TagColor
    case "research_step":
      return { color: colors["field-step-bg"], textColor: "white", borderColor: colors["field-step-bg"] } as TagColor
    default:
      return { color: colors["field-var-bg"], textColor: "white", borderColor: colors["field-var-bg"] } as TagColor
  }
}

/** Render aimd tokens to component */
const aimdProps = computed((): IAIMDWrapperProps => ({
  protocolId: props.protocolId,
  record: fieldRecordDefault.value,
  propList: fieldPropList.value,
  scopeList: scopeList.value,
  typed: previewRef.value?.env?.typed as any,
  refRecord: refRecord.value,
  tableRecord: tableRecord.value,
  varScopeRecord: varScopeRecord.value as any,
  readonly: props.readonly,
  assignerLoadingRecord: assignerLoadingRecord.value,
  assignerErrorRecord: assignerErrorRecord.value,
  assignerRequestRecord: assignerRequestRecord.value,
}))

const aimdEmit: AIMDEmits = (event, ...args) => {
  if (event === "add-row:table") {
    handleTableRowActions("add-row", ...args)
  }
  if (event === "remove-row:table") {
    handleTableRowActions("remove-row", ...args)
  }
}

const { variableList, fieldEventBus, fieldModel: componentFieldModel, restoreTableVariableRecord: restoreTableVariableRecordFn, formItemRef: aimdFormItemRef } = useAIMDProvide(aimdProps, aimdEmit)

// Assign to the store so it can be used by functions defined earlier
aimdFormItemRefStore = aimdFormItemRef

async function handlePreviewRendered() {
  const content = templateRef.value
  if (domMounted.value && lastParsedAimd.value === content) {
    return
  }

  lastParsedAimd.value = content
  setDomMounted()

  // Access template environment data directly
  if (previewRef.value) {
    const { env } = previewRef.value

    // Call the field parser with the analysis data
    handleParseField(env)

    // After parsing fields and tables, restore table variable records
    await nextTick()
    if (restoreTableVariableRecordFn) {
      restoreTableVariableRecordFn()
    }
  }
}

// Create AIMD renderers for unified system
// Map short scope codes to full scope names
const scopeMap: Record<string, string> = {
  rv: "research_variable",
  rs: "research_step",
  rc: "research_check",
  rt: "research_variable", // var_table uses research_variable scope
}

function getNodeProps(node: { id: string, scope: string, type?: string }) {
  const { id, scope, type } = node
  // Map short scope to full scope name
  const fullScope = scopeMap[scope] || scope

  if (scope === "var_table" || scope === "rt") {
    return variableList.value.find(it => it.scope === "research_variable" && it.prop === id) || null
  }
  return variableList.value.find(it => it.scope === fullScope && it.prop === id && (!type || it.type === type)) || null
}

const aimdRenderers = createPlatformAimdFormRenderers({
  getTokenProps: getNodeProps,
})
const aimdEditRenderOptions = { aimdRenderers }
const previewAimdRenderOptions = computed(() => props.readonly ? undefined : aimdEditRenderOptions)

const authStore = useAuthStore()

watchEffect(() => {
  const { userInfo } = authStore
  const record = fieldRecordDefault.value
  const propList = fieldPropList.value
  if (!record || !record.field || !userInfo || !Array.isArray(propList) || propList.length === 0) {
    return []
  }
  const { field } = record

  scopeList.value.forEach((scopeName, idx) => {
    const scopePropList = propList[idx] as string[]

    scopePropList.forEach((prop) => {
      const item = field[scopeName]?.[prop]
      if (!item) {
        return
      }

      let val: any = _cloneDeepWith(toRaw(item.value), (objVal) => {
        if (objVal instanceof Big) {
          return new Big(objVal)
        }

        return undefined
      })

      if (!val && (scopeName === "research_check" || scopeName === "research_step")) {
        val = {
          annotation: "",
          // checked: scopeName === "research_step" && !step_check ? null : false,
          // checked: item.raw?.check ? false : null,
          checked: null,
        }
      }
      if (componentFieldModel[scopeName]) {
        componentFieldModel[scopeName][prop] = { value: val }
      }
      else {
        componentFieldModel[scopeName] = { [prop]: { value: val } }
      }
    })
  })

  return () => { }
})

// Watch for changes in external fieldModel and sync to componentFieldModel
// This ensures left panel changes are reflected in the right AIMD preview
watch(
  fieldModel,
  (newFieldModel) => {
    if (!newFieldModel)
      return

    scopeList.value.forEach((scopeName) => {
      const scopeData = newFieldModel[scopeName]
      if (!scopeData)
        return

      Object.entries(scopeData).forEach(([prop, propData]) => {
        if (!propData || typeof propData !== "object")
          return

        const val = (propData as any).value
        if (componentFieldModel[scopeName]?.[prop]) {
          // Only update if value actually changed to avoid infinite loops
          const currentVal = componentFieldModel[scopeName][prop].value
          if (JSON.stringify(currentVal) !== JSON.stringify(val)) {
            // Replace the entire object to trigger reactivity
            componentFieldModel[scopeName][prop] = { value: val }
          }
        }
        else if (componentFieldModel[scopeName]) {
          // Create the prop if it doesn't exist
          componentFieldModel[scopeName][prop] = { value: val }
        }
      })
    })
  },
  { deep: true },
)

watch(
  fieldRecordDefault,
  (record) => {
    if (!record) {
      return
    }

    const propList = fieldPropList.value

    const { field } = record

    const batchList: { scope: IRecordDataKey, prop: string, value: any, assigner: any, dependent: any, info: any }[] = []

    scopeList.value.forEach((scopeName, idx) => {
      const scopePropList = propList[idx]
      scopePropList.forEach((prop) => {
        if (Array.isArray(prop)) {
          return
        }

        const item = field[scopeName]?.[prop]
        if (!item) {
          return
        }

        const { value: val, type, scope } = item
        const assigner = (item as any).assigner
        const dependent = (item as any).dependent
        const info = (item as any).info

        // Check if field has an assigner
        const hasAssigner = !!assigner
        const hasAutoAssigner = assigner && assigner.mode !== "manual"

        if (typeof val !== "undefined" && val !== null) {
          if (!(
            ((type === "float" || type === "integer" || type === "number")
              && (val.value === null || typeof val.value === "undefined"))
              || (Array.isArray(val) && val.length === 0)
          )) {
            batchList.push({
              scope: scope as IRecordDataKey,
              prop,
              value: val,
              assigner,
              dependent,
              info,
            })
          }
        }
        // Also add fields with auto assigners even if they don't have values yet
        // This ensures assigners are triggered during initial load
        else if (hasAutoAssigner) {
          batchList.push({
            scope: scope as IRecordDataKey,
            prop,
            value: undefined,
            assigner,
            dependent,
            info,
          })
        }
        // Also add manual assigner fields (for dependency checking, not execution)
        else if (hasAssigner && assigner.mode === "manual") {
          batchList.push({
            scope: scope as IRecordDataKey,
            prop,
            value: undefined,
            assigner,
            dependent,
            info,
          })
        }
      })
    })

    void nextTick(() => {
      const batchId = nanoid()
      fieldEventBus.emit("preview-field-change-batch", {
        batchId,
        list: batchList,
      })
    })
  },
  { immediate: true },
)

// watch(componentFieldModel, (val) => {
//   if (previewRef.value?.reload) {
//     previewRef.value.reload(false)
//   }
// } )

defineExpose({
  validate: wrappedValidate,
  toggle: () => {
    if (isCollapsed.value) {
      splitSize.value = 0.35
    }
    else {
      splitSize.value = 0
    }
    isCollapsed.value = !isCollapsed.value
  },
  previewRef,
  fieldRecord: fieldRecordDefault,
  fieldModel,
  restoreFieldRecord: async (recordData?: Partial<IRecordData>) => {
    if (restoreFieldRecord) {
      restoreFieldRecord(recordData)
    }

    // restoreTableVariableRecord runs after the shared preview reports a completed render.
    // after the markdown preview is mounted and fields are parsed
  },
  restoreTableVariableRecord: restoreTableVariableRecordFn,
})
</script>

<style lang="sass">
@mixin rings($duration, $delay)
  opacity: 0
  display: flex
  flex-direction: row
  justify-content: center
  align-items: center
  position: absolute
  top: -2px
  left: -2px
  right: -2px
  bottom: -2px
  content: ''
  border: 4px solid rgba(65, 129, 253, 0.6)
  border-radius: 8px
  animation-name: ripple
  animation-duration: $duration
  animation-delay: $delay
  animation-direction: alternate
  animation-iteration-count: infinite
  animation-timing-function: cubic-bezier(.65, 0, .34, 1)
  box-sizing: border-box

.aimd-field--focus
  position: relative
  .n-input__border
    border-width: 2px
    border-color: rgba(65, 129, 253, 0.6)

  &::before
    @include rings(1s, 0s)

@keyframes ripple
  from
    opacity: 1
    transform: scale3d(1, 1 , 1)

  to
    opacity: 0
    transform: scale3d(1, 1.05, 1)
</style>

<style scoped lang="sass">
@use "@styles/sass/list.sass" as *

:deep(.n-form-item-blank)
  flex-direction: column
:deep(.n-input-wrapper)
  width: 100%

:deep(.n-form-item-label__text)
  flex: 1
:deep(.n-collapse-item__header-main)
  overflow: hidden
:deep(.n-form-item-label__text)
  overflow: hidden
</style>
