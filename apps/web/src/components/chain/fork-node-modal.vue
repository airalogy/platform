<template>
  <n-modal :show="show" class="max-w-80vw min-h-20vh py-4" @update:show="handleUpdateShow">
    <n-card
      v-if="mode === 'preview' && node"
      class="card__wrapper bg-white"
      content-class="flex flex-col"
    >
      <div v-if="isForkNode" class="font-semi-bold text-lg">
        Reuse Protocol For Target
        <n-tag type="primary">
          {{ node.data.id }}
        </n-tag>
      </div>
      <n-divider class="!my-4" />

      <protocol-setup mode="fork" :protocol-info="protocolInfo" />

      <template #action>
        <div class="flex justify-end">
          <n-button ghost @click="handleClose">
            Cancel
          </n-button>
          <n-button type="primary" class="ml-5" @click="handleSubmit">
            Fork
          </n-button>
        </div>
      </template>
    </n-card>

    <n-dialog
      v-else-if="mode === 'edit' && node"
      :title="`Redirect to ${node.data.id}`"
      content="Are you sure you want to redirect to this node?"
      negative-text="Cancel"
      positive-text="Confirm"
      @close="handleClose"
      @positive-click="handleRedirect"
      @negative-click="handleClose"
    />
    <div v-else>
      {{ node }}
    </div>
  </n-modal>
</template>

<script setup lang="ts">
import type { ProtocolModels } from "@airalogy/shared/types/models"

import type { Node } from "@vue-flow/core"
import { ApplyStep, useProvideApplyProtocol } from "@/components/apply-steps/composables/useApplyProtocolState"
import ProtocolSetup from "@/components/apply-steps/protocol-setup.vue"
import { useRouterPush } from "@/composables/useRouterPush"
import { useRouteStore } from "@/store/modules/route"
import { useProtocolInfoStore } from "@/views/project-protocols/hooks/useProtocolInfoStore"
import { useClosableMessage } from "@airalogy/composables"

interface Props {
  show: boolean
  mode: "edit" | "preview" | "report"
  node: Node | null
  isForkNode: boolean
}

const props = defineProps<Props>()
const emit = defineEmits<Emit>()

interface Emit {
  (e: "update:show", value: boolean): void
  (e: "fork:complete", res: ProtocolModels.ProtocolResponseInfo, node: Node | null): void
}

const message = useClosableMessage()
const { protocolInfo } = useProtocolInfoStore()!
const { routerPushByKey } = useRouterPush()
const { addCacheRoutes } = useRouteStore()

const {
  model,
  selectedOption,
  currentStep,
  stepStatus,
  isApplying,
  applyProtocol,
} = useProvideApplyProtocol("fork")

watch(() => props.node, (val) => {
  if (val) {
    const { id, label } = val.data
    model.value.protocolName = label
    model.value.protocolUid = id
  }
}, { immediate: true, deep: true })

function handleUpdateShow(value: boolean) {
  emit("update:show", value)
}

function handleClose() {
  emit("update:show", false)
}

async function handleSubmit() {
  if (!props.node || !protocolInfo.value || !model.value.protocolId)
    return

  try {
    const res = await applyProtocol()
    if (res) {
      message.success(`Successfully forked protocol ${model.value.protocolName}`)
      emit("fork:complete", res, props.node)
      handleClose()
    }
  }
  catch (e) {
    message.error((e as Error).message)
  }
}

function handleRedirect() {
  if (!props.node)
    return

  const { data } = props.node
  if (!data || !data.source)
    return

  const { id } = data.source

  addCacheRoutes("AddProtocolRecord" as App.Global.RouteKey)
  handleClose()

  void nextTick(() => {
    void routerPushByKey("add-protocol-record-from-workflow", {
      params: { protocolId: id },
      query: {
        protocol: data.research_node.id,
        target: data.id,
      },
    })
  })
}

onMounted(() => {
  selectedOption.value = "existing"
  currentStep.value = ApplyStep.ProtocolSetup
})
</script>

<style scoped lang="sass">
.card__wrapper
  --n-padding-bottom: 0!important
  --n-action-color: transparent!important
</style>
