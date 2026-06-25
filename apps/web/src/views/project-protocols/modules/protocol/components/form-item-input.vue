<template>
  <div
    v-if="model.scope === 'research_workflow'"
    class="border border-gray-300 rounded-xl border-dashed bg-gray-50 p-4"
  >
    <div class="mb-2 text-sm text-gray-700 font-medium">
      {{ $t("page.protocol.workflow.workspaceFieldTitle") }}
    </div>
    <div class="text-sm text-gray-500">
      {{ $t("page.protocol.workflow.workspaceFieldHint") }}
    </div>
    <n-button class="mt-3" type="primary" secondary size="small" @click="handleOpenWorkflowWorkspace">
      {{ $t("page.protocol.workflow.openWorkspace") }}
    </n-button>
  </div>
  <component :is="inputComponent" v-bind="props" v-else />
</template>

<script setup lang="ts">
import type { InputPropsOptions } from "../types/input-props"
import { BuiltInType } from "@airalogy/shared/enum/airalogy"
import { isUploadFileType } from "@airalogy/shared/utils"

import BooleanSelectInput from "./inputs/boolean-select-input.vue"
import CheckboxInput from "./inputs/checkbox-input.vue"
import DatePickerInput from "./inputs/date-picker-input.vue"
import DynamicInput from "./inputs/dynamic-input.vue"
import EnumSelectInput from "./inputs/enum-select-input.vue"
import FileInput from "./inputs/file-input.vue"
import MdInput from "./inputs/md-input.vue"
import NumberInput from "./inputs/number-input.vue"
import RecordIdInput from "./inputs/record-id-input.vue"
import ResearchCheckInput from "./inputs/research-check-input.vue"
import ResearchStepInput from "./inputs/research-step-input.vue"
import TextInput from "./inputs/text-input.vue"
import TimePickerInput from "./inputs/time-picker-input.vue"

const props = defineProps<InputPropsOptions>()

const workflowWorkspace = inject<{ open: () => void } | null>("protocol-workflow-workspace", null)

function handleOpenWorkflowWorkspace() {
  workflowWorkspace?.open()
}

const inputComponent = computed(() => {
  const { enumInfo, model } = props
  const { type, scope } = model

  if (scope === "research_step") {
    return ResearchStepInput
  }
  else if (scope === "research_check") {
    return ResearchCheckInput
  }

  const builtInType = props.ajvInfo?.schema?.airalogy_built_in_type || props.ajvInfo?.schema?.airalogy_type
  if (builtInType === BuiltInType.RecordId) {
    return RecordIdInput
  }

  if (Array.isArray(enumInfo) || (!!enumInfo && Object.keys(enumInfo).length > 0)) {
    return EnumSelectInput
  }

  // Check file types using shared utility
  if (isUploadFileType(type)) {
    return FileInput
  }

  switch (type) {
    case "text":
    case "textarea":
    case "password":
      return TextInput
    case "md":
    case BuiltInType.Md:
    case BuiltInType.AiralogyMarkdown:
      return MdInput
    case "integer":
    case "float":
    case "number":
      return NumberInput
    case "time":
    case "duration":
      return TimePickerInput
    case "date":
    case "datetime":
    case BuiltInType.CurrentTime:
      return DatePickerInput
    case "boolean":
      return BooleanSelectInput
    case "checkbox":
      return CheckboxInput
    case "array":
      return DynamicInput
    default:
      return TextInput
  }
})
</script>
