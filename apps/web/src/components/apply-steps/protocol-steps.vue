<template>
  <n-steps :current="currentStep" :status="stepStatus" class="steps-custom mb-10 -mx-1">
    <n-step :title="methodTitle" :description="methodDescription">
      <template #icon>
        <n-icon>
          <icon-ion-checkmark-outline />
        </n-icon>
      </template>
    </n-step>
    <n-step :title="setupTitle" :description="setupDescription">
      <template #icon>
        <n-icon>
          <icon-tabler-settings />
        </n-icon>
      </template>
    </n-step>
    <n-step :title="allSetTitle" :description="allSetDescription">
      <template #icon>
        <n-icon>
          <icon-tabler-checks />
        </n-icon>
      </template>
    </n-step>
  </n-steps>

  <select-method
    v-if="currentStep === 1"
    :protocol-info="props.protocolInfo"
    :project-info="props.projectInfo"
  />
  <protocol-setup v-else-if="currentStep === 2" :protocol-info="props.protocolInfo" :project-info="props.projectInfo" mode="reuse" />
  <step-success v-else />

  <div v-if="currentStep !== 3" class="my-8 flex">
    <n-button v-if="currentStep !== 1 || protocolInfo?.id" ghost @click="handlePrevStep">
      {{ previousLabel }}
    </n-button>
    <n-button
      type="primary"
      :loading="isApplying"
      :disabled="isNextButtonDisabled"
      class="ml-auto"
      @click="currentStep === 2 ? handleApply() : handleNextStep()"
    >
      {{ currentStep === 2 ? createLabel : nextLabel }}
    </n-button>
  </div>
</template>

<script setup lang="ts">
import type { ValidationError } from "@airalogy/components/chat/composables/types"
import type { ProtocolModels } from "@airalogy/shared/types/models"
import type { ValidateError } from "async-validator"
import type { AxiosError } from "axios"
import type { FormInst } from "naive-ui"
import { protocolParsingEventBus } from "@/composables/useProtocolParsingEventBus"
import { $t } from "@/locales"
import { formatErrorMessage } from "@airalogy/components/chat/composables/utils"
import { useClosableMessage } from "@airalogy/composables"
import { formatValidateErrors } from "@airalogy/shared/utils/errorFormatter.js"
import { useProvideApplyProtocol } from "./composables/useApplyProtocolState"
import ProtocolSetup from "./protocol-setup.vue"
import SelectMethod from "./select-method.vue"
import StepSuccess from "./success.vue"

interface IProps {
  protocolInfo?: ProtocolModels.ProjectProtocolInfo | null
  projectInfo?: Api.Project.MyProjectInfo | null
  mode?: "fork" | "reuse"
  routeQuery?: boolean
}

const props = defineProps<IProps>()

const emit = defineEmits<IEmits>()

interface IEmits {
  (e: "cancel"): void
  (e: "success", res?: ProtocolModels.ProtocolResponseInfo | null): void
}

const hasCurrentNode = computed(() => {
  return Boolean(props.protocolInfo?.id)
})

const methodTitle = computed(() => {
  return hasCurrentNode.value
    ? $t("page.protocol.apply.method.updateTitle")
    : $t("page.protocol.apply.method.createTitle")
})
const methodDescription = computed(() => {
  return hasCurrentNode.value
    ? $t("page.protocol.apply.method.updateDescription")
    : $t("page.protocol.apply.method.createDescription")
})
const setupTitle = computed(() => $t("page.protocol.apply.setup.title"))
const setupDescription = computed(() => $t("page.protocol.apply.setup.description"))
const allSetTitle = computed(() => $t("page.protocol.apply.steps.allSetTitle"))
const allSetDescription = computed(() => $t("page.protocol.apply.steps.allSetDescription"))
const previousLabel = computed(() => $t("common.previous"))
const nextLabel = computed(() => $t("common.next"))
const createLabel = computed(() => $t("common.create"))

const formRef = ref<FormInst | null>(null)
provide("apply-protocol-form", formRef)

const {
  currentStep,
  stepStatus,
  isApplying,
  isStepValid,
  model,
  uploadModel,
  selectedOption,
  applyResult,
  applyProtocol,
} = useProvideApplyProtocol(props.mode, props.routeQuery)

const message = useClosableMessage()

const isNextButtonDisabled = computed(() => {
  return !isStepValid.value[currentStep.value]
})

async function handleNextStep() {
  if (currentStep.value < 3)
    currentStep.value++
}

async function handlePrevStep() {
  if (currentStep.value > 1) {
    currentStep.value--
  }
  else {
    emit("cancel")
  }
}

async function handleApply() {
  try {
    if (formRef.value) {
      await formRef.value.validate()
    }
  }
  catch (e) {
    const errors = formatValidateErrors(e as ValidateError[])
    message.error(errors.join("\n"))
    return
  }

  const msgInstance = message.loading($t("page.protocol.apply.action.applying"), { duration: 0 })
  try {
    isApplying.value = true

    let success = false
    if (selectedOption.value === "existing") {
      const { protocolId } = model.value
      if (!protocolId) {
        return
      }

      const res = await applyProtocol(model.value)
      if (res) {
        applyResult.value = res
        success = true
      }
    }
    else {
      const res = await applyProtocol(uploadModel.value)
      if (res) {
        applyResult.value = res
        success = true
      }
    }
    if (success) {
      msgInstance.destroy()
      // msgInstance.type = "success"
      // msgInstance.duration = 1000
      // msgInstance.content = "Protocol applied successfully"
      if (selectedOption.value === "upload-zip") {
        message.success($t("page.protocol.apply.action.uploadSuccess"))
      }
      else {
        message.success($t("page.protocol.apply.action.applySuccess"))
      }
      stepStatus.value = "finish"
      currentStep.value = 3
      emit("success", applyResult.value)
    }
    else {
      msgInstance.destroy()
      message.error($t("page.protocol.apply.action.applyFailed"))
      stepStatus.value = "error"
    }
  }
  catch (error) {
    msgInstance.destroy()
    handleError(error as AxiosError<{ detail: string | ValidationError[] }>)
  }
  finally {
    isApplying.value = false
  }
}

function handleError(error: AxiosError<{ detail: string | ValidationError[] }>) {
  const detail = formatErrorMessage(error)
  const lineMatch = detail.match(/at line (\d+)/)
  if (lineMatch) {
    protocolParsingEventBus.emit({
      message: detail,
      line: Number.parseInt(lineMatch[1]),
      fileName: "protocol.aimd", // Assuming this is the protocol file name
    })
  }
  else {
    message.error($t("page.protocol.apply.action.applyFailedWithDetail", { detail }))
  }
  stepStatus.value = "error"
}
defineExpose({
  model,
})
</script>

<style lang="sass" scoped>
.steps-custom
  :deep(.n-step)
    &:last-of-type
      flex-grow: 0
      flex-basis: fit-content

    .n-step-indicator
      @apply bg-white transition-all h-fit p-1 shadow-sm
      flex-grow: 0
      flex-basis: fit-content

    &.n-step--finish
      .n-step-indicator
        @apply bg-primary-50

      .n-step-indicator__icon
        @apply text-primary

    &.n-step--process
      .n-step-indicator
        @apply bg-primary-50 shadow-md ring-2 ring-primary/20

      .n-step-indicator__icon
        @apply text-primary
</style>
