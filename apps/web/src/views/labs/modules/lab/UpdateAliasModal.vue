<template>
  <n-form ref="formRef" :model="model" :rules="rules">
    <n-form-item path="alias" :label="props.label">
      <n-input v-model:value="model.alias" :placeholder="props.placeholder" />
    </n-form-item>
  </n-form>
</template>

<script setup lang="ts">
import type { FormInst, FormRules } from "naive-ui"

const props = withDefaults(defineProps<{
  alias?: string | null
  label?: string
  placeholder?: string
  requiredMessage?: string
  required?: boolean
}>(), {
  alias: "",
  label: "Alias",
  placeholder: "Enter Alias",
  requiredMessage: "Please enter an alias",
  required: true,
})

const formRef = ref<FormInst | null>(null)

const model = reactive({
  alias: props.alias || "",
})

const rules: FormRules = props.required
  ? {
      alias: {
        required: true,
        message: props.requiredMessage,
        trigger: ["input", "blur"],
      },
    }
  : {}

function getAlias() {
  return new Promise((resolve, reject) => {
    formRef.value?.validate((errors) => {
      if (!errors) {
        resolve(model.alias)
      }
      else {
        reject(errors)
      }
    })
  })
}

defineExpose({
  getAlias,
})
</script>
