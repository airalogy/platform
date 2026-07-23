<template>
  <section class="-mx-8">
    <header class="h-[70px] w-full flex flex-1 flex-row items-center px-8">
      <n-button quaternary class="mr-6 -ml-2" @click="handleRedirect">
        <template #icon>
          <n-icon size="28">
            <icon-tabler-arrow-left />
          </n-icon>
        </template>
      </n-button>
      <h3 v-if="route.query.target && workflowInfo?.data" class="mr-auto w-fit text-5 font-500">
        <div v-if="isReadonly" class="-mb-1">
          {{ $t("page.protocol.addRecord.viewWorkflowRecord") }}
          <n-tag type="warning">
            {{ $t("common.readOnly") }}
          </n-tag>
        </div>
        <div v-else class="-mb-1">
          {{ $t("page.protocol.addRecord.addToWorkflow") }}
        </div>
        <n-tooltip trigger="hover">
          {{ workflowInfo.data.title }}
          <template #trigger>
            <div class="flex items-center">
              <span class="mr-2">{{ $t("common.id") }}:</span>
              <n-tag type="primary">
                {{ workflowInfo.data.id }}
              </n-tag>
            </div>
          </template>
        </n-tooltip>
      </h3>
      <div v-else class="mr-auto w-fit">
        <div class="flex items-center gap-2">
          <h3 class="text-5 font-500">
            {{ $t("page.protocol.addRecord.title") }}
          </h3>
          <n-tag v-if="displayProtocolVersion" type="success" size="small">
            v{{ displayProtocolVersion }}
          </n-tag>
        </div>
        <protocol-title-section :protocol-info="protocolInfo" :title="protocolInfo?.name" :is-protocol-link="true" :show-icon="false" size="tiny" />
      </div>

      <!-- <choose-rrec-modal :rrec="rrecRef" :show="showRrec" /> -->
      <n-button v-if="isReadonly" type="warning" @click="handleCloseWindow">
        {{ $t("common.close") }}
      </n-button>
      <template v-else>
        <n-input
          v-if="route.query.record"
          v-model:value="correctionReason"
          class="mr-3 w-72"
          size="medium"
          :placeholder="$t('page.protocol.addRecord.correctionReason')"
        />
        <restore-draft-modal
          v-if="protocolId && formRef?.fieldModel" v-model:data="recordData" :field-model="formRef.fieldModel"
          :protocol-id="protocolId"
          :protocol="protocol"
          @restore:draft="handleRestoreDraft"
        />
        <n-button
          size="medium" type="primary" :disabled="loading || isReadonly || (!!route.query.record && !correctionReason.trim())" :loading="loading" class="mr-4 px-4"
          @click="handleConfirm"
        >
          {{ $t("common.submit") }}
        </n-button>
      </template>
    </header>
    <n-divider class="!mb-4 !mt-0" />
    <n-spin
      :show="loading" class="h-[calc(100vh-165px)] w-full pl-8"
      :content-class="`h-full w-full overflow-visible ${protocol ? '' : ' flex-center flex-col'}`"
    >
      <protocol-add-record-form
        v-if="protocol && protocolInfo && protocolId" ref="formRef" v-model:collapsed="isCollapsed" :protocol="protocol"
        :protocol-id="protocolId"
        :readonly="isReadonly"
        :record-data="recordData"
        @update:field="handleUpdateField"
        @update:split-size="handleUpdateSize"
      >
        <!-- <template #prefix>
          <div class="mb-2 ml-2 w-fit w-full rounded px-4 text-[1.125rem] text-white leading-10">
            <n-collapse v-model:expanded-names="expandedNames" display-directive="show" arrow-placement="right">
              <n-collapse-item title="Previous Records" name="metadata">
                <record-comment v-model="metadata" @confirm="handleCollapseMetadata" />
              </n-collapse-item>
            </n-collapse>
          </div>
        </template> -->
      </protocol-add-record-form>
      <n-upload
        v-else-if="!loading" :headers="{ 'auth-token': authStore.token }" :action="uploadAction" class="w-fit"
        directory-dnd :show-file-list="false" @finish="handleFinish" @error="handleUploadFailed"
      >
        <div class="mr-5 text-5">
          {{ $t("page.protocol.addRecord.noProtocol") }}
        </div>
        <n-button class="mr-5">
          {{ $t("page.protocol.addRecord.uploadPackage") }}
          <template #icon>
            <upload-icon />
          </template>
        </n-button>
      </n-upload>
    </n-spin>
  </section>
</template>

<script setup lang="ts">
import type { IRecordData, IRecordDataKey } from "@airalogy/aimd-core/types"
import type { ProtocolModels } from "@airalogy/shared/types"
import type { ValidateError } from "async-validator"
import type { OnError } from "naive-ui/es/upload/src/interface"

import type { ShallowRef } from "vue"
import type { ExtractResult, FieldRecord } from "./modules/protocol/helpers/parseFieldStructure"
import type { IRecordDataItem } from "./types"

import { useBoolean, useGlobalBeforeUnload, useLoading, useShowModal } from "@/composables"
import { useRouterPush } from "@/composables/useRouterPush"
import { getProtocolRecordReport, postNewResearchRecord, postValidateRecord, putUpdateResearchRecord, transformFields } from "@/service/api/project-protocols"

import { baseURL } from "@/service/request"
import { useAuthStore } from "@/store/modules/auth"
import { useRouteStore } from "@/store/modules/route"
import { useProtocolWorkflowStore } from "@/store/modules/workflow"
import { useBeforeUnload, useClosableMessage } from "@airalogy/composables"
import { useThemeStore } from "@airalogy/composables/theme"
import { formatPydanticErrors, formatValidateErrors, type PydanticError } from "@airalogy/shared/utils/errorFormatter.js"
import { get as _get, set as _set } from "lodash-es"
import { type UploadOnFinish, useDialog } from "naive-ui"
import { NButton } from "naive-ui/es/button"
import { nanoid } from "nanoid"
import { useI18n } from "vue-i18n"
import { useProvideProtocolInfoStore } from "./hooks/useProtocolInfoStore"
import { useDraftManagement } from "./modules/protocol/composables/useDraftManagement"
import ProtocolAddRecordForm from "./modules/protocol/protocol-add-record-form.vue"
import { assignFieldValue, extractAssetId } from "./utils"

defineOptions({ name: "AddProtocolRecord" })

const emits = defineEmits<IEmits>()

interface IEmits {
  (
    e: "modal:new-record",
    val: {
      labId: string
      labName: string
      id: string
      name: string
    },
  ): void
  (e: "modal:close"): void
  (e: "modal:open"): void
}
const dialog = useDialog()
const { t } = useI18n()
const { isShown, showModal, hideModal } = useShowModal()

const route = useRoute()
const router = useRouter()

const themeStore = useThemeStore()
const workflowStore = useProtocolWorkflowStore()
const workflowInfo = computed(() => workflowStore.getWorkflow(route.query.chain as string))

const { removeCacheRoutes } = useRouteStore()
const { routerPushByKey } = useRouterPush()

function handleUpdateShow(show: boolean) {
  if (show) {
    showModal()
    return
  }

  dialog.warning({
    title: t("common.discardTitle"),
    content: t("common.discardWarning"),
    positiveText: t("common.discardConfirm"),
    negativeText: t("common.discardCancel"),
    transformOrigin: "center",
    onPositiveClick: () => {
      hideModal()
      emits("modal:close")
    },
  })
}

function handleCancel() {
  hideModal()
}

const protocol = ref<ProtocolModels.ProtocolInfo | null>(null)
const editingProtocolVersion = ref<string | null>(null)
const correctionReason = ref("")

const formRef = ref<{
  validate: () => any
  toggle: () => void
  fieldRecord: ShallowRef<ExtractResult | null>
  fieldModel: FieldRecord
  restoreFieldRecord: (data?: Partial<IRecordData>) => void
} | null>(null)

const instanceId = nanoid()
provide("protocol-workflow-channel", { id: instanceId })

const message = useClosableMessage()
const { post, channel } = useBroadcastChannel({ name: `workflow-${route.query.chain || nanoid()}` })

const authStore = useAuthStore()

const { endLoading, loading, startLoading } = useLoading()
const { fetchProtocolInfoByUid, protocolInfo, protocolUid, protocolId } = useProvideProtocolInfoStore(null)
const displayProtocolVersion = computed(() =>
  editingProtocolVersion.value
  || (protocol.value as ProtocolModels.ProjectProtocolInfo | null)?.metadata?.version
  || protocolInfo.value?.latest_version
  || "",
)

const uploadAction = computed(() => {
  return protocolUid.value ? `${baseURL}/protocols` : ""
})

const recordData = ref<Partial<IRecordData>>({})
const { bool: isReadonly, setTrue: setReadonly } = useBoolean()

const { saveDraft, deleteDraft } = useDraftManagement(protocol, recordData)

const AUTOSAVE_DEBOUNCE_MS = 4000
const AUTOSAVE_INTERVAL_MS = 60_000

const autosaveState = reactive({
  lastSignature: "",
  hasPendingChanges: false,
  lastSavedAt: 0,
})

const globalBeforeUnloadRegistry = useGlobalBeforeUnload()
const { unregister } = globalBeforeUnloadRegistry
const { cleanup } = useBeforeUnload(() => autosaveState.hasPendingChanges, {
  id: route.fullPath,
})

type AutosaveReason = "debounce" | "interval" | "visibility" | "unload"

function canAutosave() {
  return Boolean(protocolId.value) && !isReadonly.value
}

function getDraftSignature(data: Partial<IRecordData> = recordData.value) {
  try {
    return JSON.stringify(toRaw(data ?? {}))
  }
  catch (error) {
    console.warn("Failed to serialize draft data:", error)
    return ""
  }
}

const triggerAutosave = useDebounceFn(() => flushAutosave("debounce"), AUTOSAVE_DEBOUNCE_MS)
function cancelAutosave() {
  const handler = triggerAutosave as typeof triggerAutosave & { cancel?: () => void }
  if (typeof handler.cancel === "function") {
    handler.cancel()
  }
}

function resetAutosaveBaseline(data: Partial<IRecordData> = recordData.value) {
  autosaveState.lastSignature = getDraftSignature(data)
  autosaveState.hasPendingChanges = false
  cancelAutosave()
}

function markAutosavePending() {
  if (!canAutosave()) {
    return
  }
  autosaveState.hasPendingChanges = true
  triggerAutosave()
}

function flushAutosave(reason: AutosaveReason, force = false) {
  void reason
  if (!canAutosave()) {
    return
  }

  if (!autosaveState.hasPendingChanges && !force) {
    return
  }

  const signature = getDraftSignature()
  if (!signature || signature === autosaveState.lastSignature) {
    autosaveState.hasPendingChanges = false
    return
  }

  if (!protocolId.value) {
    return
  }

  saveDraft(protocolId.value, recordData.value, { silent: true })
  autosaveState.lastSignature = signature
  autosaveState.hasPendingChanges = false
  autosaveState.lastSavedAt = Date.now()
}

function clearDraftAfterSubmit() {
  if (!protocolId.value) {
    return
  }
  deleteDraft(protocolId.value)
  resetAutosaveBaseline(recordData.value)
  message.success(t("page.protocol.draft.cleared"))
}

watch(recordData, () => {
  markAutosavePending()
}, { deep: true })

watch(isReadonly, (val) => {
  if (val) {
    autosaveState.hasPendingChanges = false
    cancelAutosave()
  }
})

const autosaveIntervalId = ref<number | null>(null)

useEventListener(document, "visibilitychange", () => {
  if (document.visibilityState === "hidden") {
    flushAutosave("visibility", true)
  }
})

useEventListener(window, "beforeunload", () => {
  flushAutosave("unload", true)
})

function handleUpdateField(payload: {
  scope: IRecordDataKey
  prop: string
  value: IRecordDataItem
  info?: any
}) {
  const { scope, prop, value, info } = payload

  assignFieldValue(recordData, scope, prop, value, info)
}

const handleUploadFailed: OnError = (options) => {
  // TODO: emit event
  const { event } = options
  const { response, statusText, status } = event?.target as XMLHttpRequest

  if (response.error) {
    message.error(response.error)
  }
  else {
    message.error(t("page.protocol.addRecord.uploadError", { status, statusText }), {
      closable: true,
      duration: 0,
    })
  }
}

const handleFinish: UploadOnFinish = (options) => {
  message.success(t("page.protocol.addRecord.uploadSuccess"))
  // TODO: emit event

  const { event } = options
  const { response } = event?.target as XMLHttpRequest

  try {
    const { data } = JSON.parse(response) as { data: ProtocolModels.ProtocolInfo }
    protocol.value = data
  }
  catch (e) {
    message.error(t("page.protocol.addRecord.uploadFailed"))
  }
}

interface ResourceCommitSummary {
  field: string
  role: string
  label: string
  quantity?: string
  unit?: string
  container?: string
  booking?: string
}

function resourceCommitSummary(
  values: Record<string, any>,
): ResourceCommitSummary[] {
  const fields = (protocol.value?.fields || {}) as Record<string, any>
  const templates = fields.templates && typeof fields.templates === "object"
    ? fields.templates
    : fields
  const definitions = templates.var_definitions
    || templates.vars
    || templates.var
    || []
  const summaries: ResourceCommitSummary[] = []
  for (const definition of definitions) {
    const type = String(definition?.type || definition?.type_annotation || "")
    if (!type.includes("ResourceRef"))
      continue
    const field = String(definition?.id || definition?.name || "")
    const value = values[field]
    if (!field || !value || typeof value !== "object")
      continue
    const kwargs = definition?.kwargs && typeof definition.kwargs === "object"
      ? definition.kwargs
      : {}
    const role = String(kwargs.resource_role || "reference")
    if (!["input", "output", "equipment"].includes(role))
      continue
    const quantityField = kwargs.quantity_field
      ? String(kwargs.quantity_field).replace(/^var\./, "")
      : ""
    const quantity = quantityField ? values[quantityField] : value.quantity
    summaries.push({
      field,
      role,
      label: String(value.label || value.snapshot?.name || value.id),
      quantity: quantity === null || quantity === undefined
        ? undefined
        : String(quantity),
      unit: value.unit ? String(value.unit) : undefined,
      container: value.container_id ? String(value.container_id) : undefined,
      booking: value.booking_id ? String(value.booking_id) : undefined,
    })
  }
  return summaries
}

function confirmResourceCommit(
  values: Record<string, any>,
): Promise<boolean> {
  const summaries = resourceCommitSummary(values)
  if (!summaries.length)
    return Promise.resolve(true)
  return new Promise((resolve) => {
    let settled = false
    const settle = (value: boolean) => {
      if (!settled) {
        settled = true
        resolve(value)
      }
    }
    dialog.warning({
      title: t("page.protocol.addRecord.resourceCommitTitle"),
      content: () => h(
        "div",
        { class: "space-y-2" },
        [
          h("p", t("page.protocol.addRecord.resourceCommitDescription")),
          ...summaries.map(item =>
            h("div", { class: "rounded border p-2 text-sm" }, [
              h("strong", `${item.field} · ${item.role}`),
              h("div", item.label),
              item.quantity
                ? h("div", `${item.quantity} ${item.unit || ""}`.trim())
                : null,
              item.container
                ? h("div", `${t("page.protocol.addRecord.resourceContainer")}: ${item.container}`)
                : null,
              item.booking
                ? h("div", `${t("page.protocol.addRecord.resourceBooking")}: ${item.booking}`)
                : null,
            ]),
          ),
        ],
      ),
      positiveText: t("page.protocol.addRecord.confirmResourceCommit"),
      negativeText: t("common.cancel"),
      onPositiveClick: () => settle(true),
      onNegativeClick: () => settle(false),
      onClose: () => settle(false),
    })
  })
}

async function handleConfirm() {
  if (!formRef.value || isReadonly.value) {
    return
  }
  startLoading()

  try {
    await formRef.value.validate()

    if (!protocolId.value) {
      return
    }
    const { research_check, research_result, research_step, research_variable: researchVariable } = recordData.value

    const payload = extractAssetId(toRaw(researchVariable)) || {}

    const { data: result, error: validateError } = await postValidateRecord(
      protocolId.value,
      payload,
      editingProtocolVersion.value || undefined,
    )

    if (validateError) {
      if (Array.isArray(validateError)) {
        // Format validation errors for better display
        const errors = formatPydanticErrors(validateError as PydanticError[])

        message.error(errors.join("\n"))
      }
      else {
        const errMsg = (validateError.response?.data as any)?.detail || validateError.message
        message.error(errMsg)
      }
      return
    }

    if (!result) {
      return
    }

    const { research_variable = {} } = result
    // const preparedReport = formRef.value?.preparedReport()
    const { record } = route.query
    if (!record && !(await confirmResourceCommit(research_variable))) {
      return
    }

    const { data, error } = await (record
      ? putUpdateResearchRecord(protocolId.value, record as string, {
        research_variable: research_variable as any,
        research_check: research_check as any,
        research_result: research_result as any,
        research_step: research_step as any,
        report: "",
        revision_reason: correctionReason.value.trim(),
      })
      : postNewResearchRecord(protocolId.value, {
        research_variable: research_variable as any,
        research_check: research_check as any,
        research_result: research_result as any,
        research_step: research_step as any,
        report: "",
      }))

    if (data) {
      clearDraftAfterSubmit()
      const { chain, target } = route.query
      const targetId = target as string
      const chainInfo = workflowStore.getWorkflow(chain as string)
      if (chainInfo && targetId) {
        const { data: chainInfoData, model, flowNodes } = chainInfo

        const uid = protocolInfo.value?.uid
        const airalogyProtocolId = protocolInfo.value?.airalogy_id
        if (uid || airalogyProtocolId) {
          const targetNode = flowNodes.find(({ airalogy_protocol_id }) =>
            airalogy_protocol_id === uid || airalogy_protocol_id === airalogyProtocolId,
          )

          if (targetNode) {
            targetNode.status = "done"
          }
        }

        post({ action: "showIntermediate", data, source: target, id: instanceId })
        setReadonly()
        dialog.success({
          title: t("page.protocol.addRecord.workflowContinueTitle"),
          content: t("page.protocol.addRecord.workflowContinueContent"),
          negativeText: t("page.protocol.addRecord.workflowStay"),
          positiveText: t("common.close"),
          onPositiveClick(e) {
            if (window.opener) {
              window.opener.focus()
              window.close()
            }
          },
        })
      }
      else if (protocolInfo.value) {
        message.success(t("page.protocol.addRecord.createSuccess"))
        const { lab, project, uid } = protocolInfo.value
        cleanup()

        unregister(route.fullPath)
        await routerPushByKey("protocol-records", {
          params: { protocolUid: uid, labUid: lab.uid, projectUid: project.uid },
        })
      }
      hideModal()
    }
    else if (error) {
      // message.error(error.message)
    }
  }
  catch (e) {
    if (e instanceof Error) {
      message.error(e.message, {
        closable: true,
        duration: 8000,
      })
      return
    }

    const errors = formatValidateErrors(e as ValidateError[])

    message.error(errors.join("\n"), {
      closable: true,
      duration: 8000,
    })
  }
  finally {
    endLoading()
  }
}

const isCollapsed = ref(false)
function handleToggle() {
  const toggle = formRef.value?.toggle
  if (typeof toggle === "function") {
    toggle()
  }
}

const splitSize = ref<string | null>("35%")
function handleUpdateSize(value: string | number) {
  const percent = Number(value)
  if (Number.isNaN(percent)) {
    return
  }

  void nextTick(() => {
    if (isCollapsed.value) {
      splitSize.value = "0%"
    }
    else {
      splitSize.value = `${percent * 100}%`
    }
  })
}

const rrecRef = computed(() => {
  if (!protocolInfo.value)
    return null
  const { properties } = (protocolInfo.value.json_schema?.research_variable
    || {}) as Record<string, any>

  if (!properties) {
    return null
  }

  const { rrec } = properties as {
    rrec?: { default: { rrec_airalogy_id: string, metadata: string } }
  }

  return rrec?.default ?? null
})
const { bool: showRrec, setTrue: showRrecInfo, setFalse: hideRrecInfo } = useBoolean()
function handleShowRrec() {
  showRrecInfo()
}

function handleRedirect() {
  const { lab, project, uid } = protocolInfo.value || {}
  if (lab?.uid && project?.uid && uid) {
    void routerPushByKey("protocol-detail", {
      params: { labUid: lab.uid, projectUid: project.uid, protocolUid: uid },
    })
  }
  else {
    router.back()
  }
}

function handleCloseWindow() {
  dialog.warning({
    title: t("page.protocol.addRecord.closeWindowTitle"),
    content: t("page.protocol.addRecord.closeWindowContent"),
    positiveText: t("common.confirm"),
    negativeText: t("common.cancel"),
    onPositiveClick() {
      window.close()
    },
  })
}

onMounted(async () => {
  if (protocol.value) {
    return
  }

  startLoading()
  const { labUid, projectUid, protocolUid } = route.params as {
    labUid: string
    projectUid: string
    protocolUid: string
  }

  // Always fetch the latest version without cache
  // Set memoize to false to ensure we get fresh data from backend
  const info = await fetchProtocolInfoByUid({ labUid, projectUid, protocolUid }, true, false)

  if (info) {
    await nextTick(() => {
      const { record: recordId } = route.query
      if (recordId) {
        fetchRecord()
      }
      else {
        protocol.value = (info as ProtocolModels.ProtocolInfo) || null
      }
    })
  }
  endLoading()
})

onMounted(() => {
  themeStore.footer.visible = false
})

onMounted(() => {
  resetAutosaveBaseline(recordData.value)
  autosaveIntervalId.value = window.setInterval(() => {
    flushAutosave("interval")
  }, AUTOSAVE_INTERVAL_MS)
})

onBeforeUnmount(() => {
  themeStore.footer.visible = true
})

onBeforeUnmount(() => {
  flushAutosave("unload", true)
  if (autosaveIntervalId.value) {
    window.clearInterval(autosaveIntervalId.value)
    autosaveIntervalId.value = null
  }
})

onActivated(() => {
  removeCacheRoutes("AddResearchRecord" as any)
})

// const editorStore = useEditorStore()
// const { setFallbackResults, setMinisearch } = editorStore

// watch(protocolInfo, (val) => {
//   if (val) {
//     setFallbackResults("fields", [{
//       id: "fields",
//       title: "Fields",
//       description: "Fields",
//     }])

//     const minisearch = new MiniSearch({
//       fields: ["title", "description"],
//       storeFields: ["id", "title", "description"],
//     })

//     setMinisearch("fields", minisearch)

//     minisearch.addAll([{
//       id: "fields",
//       title: "Fields",
//       description: "Fields",
//       providerTitle: "fields",
//     }])
//   }
// }, { immediate: true })
const submenuBus = useEventBus<"request:protocol/getFields" | "response:protocol/getFields" | "refreshSubmenuItems", { provider: Chat.ContextProviderName } | ExtractResult>("submenu-eventbus")

submenuBus.on((event) => {
  if (event === "request:protocol/getFields") {
    if (formRef.value?.fieldRecord) {
      submenuBus.emit("response:protocol/getFields", formRef.value.fieldRecord)
    }
  }
})

watch(() => formRef.value?.fieldRecord, (val) => {
  if (val) {
    submenuBus.emit("refreshSubmenuItems", { provider: "protocol" })
  }
})

const { error, warning } = useClosableMessage()
async function handleRestoreDraft(data: Partial<IRecordData>) {
  const { restoreFieldRecord, validate } = formRef.value || {}
  if (!restoreFieldRecord) {
    warning(t("page.protocol.addRecord.noDraftFound"))
    return
  }

  try {
    restoreFieldRecord(data)
    recordData.value = data
    resetAutosaveBaseline(recordData.value)

    // await nextTick()
    // if (validate) {
    //   await validate()
    // }
  }
  catch (e) {
    if (e instanceof Error) {
      error(e.message)
    }
    if (Array.isArray(e)) {
      const errors = formatValidateErrors(e as ValidateError[])

      message.error(errors.join("\n"))
    }
  }
}

async function fetchRecord() {
  const { record: recordId, recordVersion } = route.query
  if (!recordId || !protocolInfo.value) {
    return
  }

  try {
    startLoading()

    const { id: protocolId } = protocolInfo.value

    const recordRes = await getProtocolRecordReport({
      recordId: recordId as string,
      protocolId,
      version: String(recordVersion || "1"),
    })

    const { labUid, projectUid, protocolUid } = route.params as {
      labUid: string
      projectUid: string
      protocolUid: string
    }
    const sourceVersion = recordRes.metadata.protocol_version
    const versionedInfo = protocolInfo.value.metadata?.version === sourceVersion
      ? protocolInfo.value
      : await fetchProtocolInfoByUid(
        { labUid, projectUid, protocolUid, version: sourceVersion },
        true,
        false,
      )
    const protocolData = versionedInfo
      ? transformFields(versionedInfo as ProtocolModels.ProjectProtocolInfo)
      : null

    const { check, step, var: varData } = recordRes.data

    const convertedData = { research_check: check, research_step: step, research_variable: varData } as Partial<IRecordData>

    const schema = protocolData?.json_schema
    if (schema) {
      for (const key in varData) {
        const targetSchema = _get(schema, ["research_variable", key, "properties"])
        if (targetSchema) {
          _set(convertedData, ["research_variable", key, "properties"], targetSchema)
        }
      }
    }

    protocol.value = protocolData
    editingProtocolVersion.value = sourceVersion
    recordData.value = convertedData
    resetAutosaveBaseline(recordData.value)
  }
  catch (e) {
    if (e instanceof Error) {
      message.error(e.message)
    }
  }
  finally {
    endLoading()
  }
}

const metadata = ref({ rrec: [], comment: "" })
const expandedNames = ref<string[]>([])
function handleCollapseMetadata() {
  expandedNames.value = []
}

const { load, unload } = useStyleTag(":root {overflow: hidden;}")

onBeforeMount(() => {
  load()
})

onBeforeUnmount(() => {
  unload()
})
</script>

<style scoped lang="sass">
@use "@styles/sass/list.sass" as *

:deep(.n-form-item)
  position: relative

:deep(.n-drawer-header__main)
  flex: 1
:deep(.n-drawer-body-content-wrapper)
  padding: 0!important
</style>
