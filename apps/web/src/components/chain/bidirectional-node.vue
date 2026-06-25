<template>
  <flow-handle
    v-if="
      direction === 'single-input' || direction === 'bidirectional-input' || direction === 'in-out'
    "
    type="target"
    :position="props.targetPosition"
    :connectable="props.connectable"
    :is-valid-connection="props.isValidTargetPos"
  />
  <n-spin :show="loading">
    <div v-if="props.mode === 'edit'" class="absolute bottom-full h-fit w-full flex-center pb-1">
      <div class="mr-auto rounded-2 bg-[#F1F4F6] px-4 py-2 color-base-text">
        {{ $t("page.protocol.workflow.protocolIndex", { index: data.sequence }) }}
      </div>
      <div class="mr-2 whitespace-nowrap color-text-secondary">
        {{ $t("page.protocol.apply.setupForm.protocolIdLabel") }}:
      </div>
      <n-button
        text
        type="primary"
        size="tiny"
        :disabled="loading"
        icon-placement="right"
        class="max-w-1/2 overflow-hidden color-text-secondary hover:color-primary"
        @click.stop="handleRedirect"
      >
        <n-ellipsis>
          {{ data.id }}
        </n-ellipsis>
        <template #icon>
          <n-icon>
            <icon-ion-open-outline />
          </n-icon>
        </template>
      </n-button>
    </div>
    <div
      class="chain-node__wrapper"
      :class="{
        'chain-node__wrapper--success': hasRecord,
        'chain-node__wrapper--error': !loading && !data.source && !data.target,
        'chain-node__wrapper--warning': !loading && data.source && !data.target,
      }"
    >
      <template v-if="props.mode === 'preview'">
        <div v-if="data.target" class="max-w-70">
          <div class="text-bold text-lg">
            {{ data.target.name }}
          </div>
          <n-button
            text
            icon-placement="right"
            @click="handleRedirect"
          >
            {{ data.target.uid }}
            <template #icon>
              <n-icon size="16">
                <icon-ion-open-outline />
              </n-icon>
            </template>
          </n-button>
        </div>
        <template v-else>
          <div class="font-semi-bold max-w-65 text-lg">
            {{ label }}
          </div>
          <n-text class="mt-1 h-full flex-center">
            <n-ellipsis class="text-rtl mr-2 max-w-25" :line-clamp="2">
              {{ data.id }}
            </n-ellipsis>
            <n-button ghost type="primary" size="tiny" :disabled="loading" @click.stop="handleFork">
              {{ $t("common.reuse") }}
            </n-button>
          </n-text>
        </template>
      </template>
      <div v-if="props.mode === 'edit'" class="max-w-80">
        <div v-if="data.source" class="relative h-full w-full">
          <div
            class="absolute bottom-[calc(100%+12px)] left-0 right-0 flex flex-row flex-wrap-reverse pb-2"
          >
            <n-tag class="mt-2">
              <span class="whitespace-pre-wrap">
                {{ data.source.name }}
              </span>
            </n-tag>
            <n-tag class="ml-auto">
              <span class="mr-2">{{ $t("common.id") }}:</span>
              <n-ellipsis class="max-w-20" :line-clamp="1">
                {{ data.source.uid }}
              </n-ellipsis>
            </n-tag>
          </div>
          <div class="min-w-40 text-lg">
            {{ data.source.name }}
          </div>
        </div>
        <div class="font-semi-bold text-lg">
          {{ label }}
        </div>
      </div>
    </div>
  </n-spin>
  <flow-handle
    v-if="
      direction === 'single-output'
        || direction === 'bidirectional-output'
        || direction === 'in-out'
    "
    type="source"
    :position="props.sourcePosition"
    :connectable="props.connectable"
    :is-valid-connection="props.isValidSourcePos"
  />
</template>

<script setup lang="ts">
import type { ProtocolModels } from "@airalogy/shared/types/models"

import type { NodeProps } from "@vue-flow/core"
import { useLoading } from "@/composables"
import { useRouterPush } from "@/composables/useRouterPush"
import { getProtocolInfoByUid } from "@/service/api/project-protocols"
import { useProtocolWorkflowStore } from "@/store/modules/workflow"
import { useProtocolInfoStore } from "@/views/project-protocols/hooks/useProtocolInfoStore"
import { useClosableMessage } from "@airalogy/composables"
import { type IAiralogyIdBaseItem, parseAiralogyId } from "@airalogy/shared/utils/parseAiralogyId"
import { Handle as FlowHandle } from "@vue-flow/core"

defineOptions({ inheritAttrs: false })

const props = defineProps<IProps>()

const emit = defineEmits<IEmits>()

interface IProps extends NodeProps {
  onUpdateNodeInternals: () => void
  data: {
    label: string
    id: string
    protocol: ProtocolModels.ProtocolInfo
    source: ProtocolModels.ProjectProtocolInfo | null
    target: ProtocolModels.ProjectProtocolInfo | null
    sequence?: number
  }
  direction:
    | "single-input"
    | "single-output"
    | "bidirectional"
    | "bidirectional-input"
    | "bidirectional-output"
    | "in-out"
  mode?: "edit" | "preview" | "report"
  storeId?: string
}

interface IEmits {
  (e: "update:data", data: IProps["data"]): void
  (e: "update:layout"): void
  (e: "fork:node", id: string): void
}
const data = useVModel(props, "data", emit, { passive: true, deep: true })

const workflowStore = useProtocolWorkflowStore()
const message = useClosableMessage()
const workflowInfo = computed(() => workflowStore.getWorkflow(props.storeId))
const hasRecord = computed(() => {
  if (!workflowInfo.value) {
    return false
  }

  const { flowNodes } = workflowInfo.value
  const node = flowNodes?.find(node => node.airalogy_protocol_id === props.id)

  if (node) {
    return node.status === "done"
  }

  return false
})

const label = computed(() => {
  const { source, id, label: val } = data.value
  if (source) {
    return source.name
  }

  return val || id
})

const state = inject<{
  apiKey: Ref<string | null>
  mappings: Ref<Record<"source" | "target", string>[]>
  initialized: Ref<boolean>
}>("chain-state")

const { protocolInfo } = useProtocolInfoStore()!

const { loading, startLoading, endLoading } = useLoading(true)
const airalogyIdItem = computed<IAiralogyIdBaseItem | null>(() => {
  const { id } = data.value

  if (!id) {
    return null
  }
  if (!id.includes(".") && protocolInfo.value) {
    const { lab, project } = protocolInfo.value

    return {
      type: "rn",
      lab: lab.uid,
      project: project.uid,
      node: id,
      version: { main: "", minor: "", patch: "" },
    }
  }

  return parseAiralogyId(id) as IAiralogyIdBaseItem | null
})

async function handleFetchSourceData() {
  const idItem = airalogyIdItem.value

  if (!idItem) {
    return null
  }

  const { lab, node, project } = idItem

  const res = await getProtocolInfoByUid({
    labUid: lab,
    projectUid: project,
    protocolUid: node,
  }, false)
  if (res.data) {
    data.value.source = res.data as any
  }

  return res
}

async function handleFetchTargetData() {
  if (!airalogyIdItem.value || !state?.initialized || !protocolInfo.value) {
    return null
  }

  const { lab, node, project } = airalogyIdItem.value

  const res = await getProtocolInfoByUid({
    labUid: lab || protocolInfo.value.lab.uid,
    projectUid: project || protocolInfo.value.project.uid,
    protocolUid: node,
  }, false)

  if (res.data) {
    data.value.target = res.data as any
  }

  return res
  // const mappings = state?.mappings?.value

  // if (mappings) {
  //   const targetMapping = mappings.find(it => it.source === `${lab}.${project}.${node}`)

  //   if (targetMapping) {
  //     const res = await getResearchInfoByRNId(`airalogy.rn.${targetMapping.target}`)
  //     if (res) {
  //       data.value.target = res
  //     }
  //   }
  // }

  // TODO: create target project
}

function handleFork() {
  emit("fork:node", props.id)
}

const { routerPushByKey } = useRouterPush()

async function handleRedirect() {
  const { target } = data.value
  if (target) {
    const { lab, project, uid } = target

    await routerPushByKey("protocol-info", {
      params: {
        labUid: lab.uid,
        projectUid: project.uid,
        protocolUid: uid,
      },
    })
  }
}

watch(
  () => data.value.target,
  async (target) => {
    if (target) {
      return
    }

    startLoading()
    try {
      const targetData = await handleFetchTargetData()

      if (!targetData) {
        const sourceData = await handleFetchSourceData()
        if (!sourceData) {
          message.error(`Target protocol ${data.value.id} not found`)
        }
      }
    }
    catch (e) {
      // NODE
    }
    finally {
      endLoading()
      emit("update:layout")
    }
  },
  { immediate: true },
)

// watch(
//   () => state?.mappings.value,
//   async mappings => {
//     startLoading()
//     await handleFetchTargetData()
//     endLoading()
//   },
//   { immediate: true },
// )
// watch(
//   () => state?.apiKey.value,
//   async key => {
//     if (key) {
//       try {
//         await handleFetchSourceData()
//       } catch (e) {
//         // NODE
//       } finally {
//         endLoading()
//         nextTick(() => {
//           props.onUpdateNodeInternals()
//         })
//       }
//     }
//   },
//   { immediate: true },
// )
</script>

<style scoped lang="sass">
.chain-node__wrapper
  padding: 10px
  background: var(--chain-node-bg)
  border-color: var(--chain-node-color, #1a192b)
  border-radius: 8px
  font-size: 12px
  text-align: center
  border-width: 1px
  border-style: solid
  color: var(--vf-node-text)

  &:hover
    box-shadow: 0 1px 4px 1px rgba(0, 0, 0, 0.08)

  &--error
    --chain-node-color: #{$danger-color}

  &--warning
    --chain-node-color: #{$warning-color}

  &--success
    --chain-node-color: #{$success-color}

.chain-node__handler
  &--error
    --chain-node-color: #{$danger-color}

:deep(.chain__breadcrumb ul)
  padding-left: 0!important

  margin-bottom: 0!important

:deep(.n-breadcrumb-item__separator)
  margin: 0 2px!important

.chain__breadcrumb
  :deep(ul)
    display: flex
    flex-wrap: wrap
  li
    margin-bottom: 0!important
</style>
