<template>
  <n-form ref="formRef" :model="model" :rules="rules" size="medium" class="w-full space-y-4">
    <!-- <div class="space-y-6">
      <div v-for="(editor, index) in editors" :key="editor.id" class="space-y-2">
        <div class="flex items-center justify-between">
          <span class="text-base font-medium">{{ editor.label }}</span>
          <n-button size="tiny" quaternary @click="() => handlePaste(editor.id)">
            Paste
          </n-button>
        </div>
        <tiptap-code-input
          v-model="model[editor.id]" :placeholder="editor.placeholder" :code-language="editor.language"
          :enable-syntax="true" class="h-[200px] overflow-y-auto"
        />
        <n-text v-if="errors[editor.id]" class="text-error">
          {{ errors[editor.id] }}
        </n-text>
      </div>
    </div> -->

    <monaco-editor :editor-id="0" />
  </n-form>
</template>

<script setup lang="ts">
import type { FormInst } from "naive-ui"
import MonacoEditor from "@/components/monaco-editor/layout.vue"
import { useFormRules } from "@/composables"
import { reactive, ref } from "vue"

interface Props {
  modelValue?: Record<string, any>
}

interface Emits {
  (e: "update:modelValue", value: Record<string, any>): void
  (e: "validated", value: boolean): void
}

type EditorId = "protocol" | "model" | "assigner"

interface EditorConfig {
  id: EditorId
  label: string
  placeholder: string
  language: string
}

interface EditorModel {
  protocol: string
  model: string
  assigner: string
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const formRef = ref<FormInst | null>(null)
const { defaultRequiredRule } = useFormRules()

const editors: EditorConfig[] = [
  {
    id: "protocol",
    label: "Protocol (protocol.aimd)",
    placeholder: "Enter or paste your protocol.aimd content here...",
    language: "markdown",
  },
  {
    id: "model",
    label: "Model (model.py)",
    placeholder: "Enter or paste your model.py content here...",
    language: "python",
  },
  {
    id: "assigner",
    label: "Assigner (assigner.py)",
    placeholder: "Enter or paste your assigner.py content here...",
    language: "python",
  },
]

const model = reactive<EditorModel>({
  protocol: "",
  model: "",
  assigner: "",
})

const errors = reactive<Record<EditorId, string>>({
  protocol: "",
  model: "",
  assigner: "",
})

const rules = {
  protocol: [defaultRequiredRule],
  model: [defaultRequiredRule],
  assigner: [defaultRequiredRule],
}

async function handlePaste(editorId: EditorId) {
  try {
    const text = await navigator.clipboard.readText()
    model[editorId] = text
  }
  catch (error) {
    // Handle clipboard read error
    console.error("Failed to read clipboard:", error)
  }
}

async function validate() {
  return new Promise((resolve) => {
    formRef.value?.validate((errors) => {
      const isValid = !errors
      emit("validated", isValid)
      resolve(isValid)
    })
  })
}

// Watch for model changes and emit updates
watch(
  () => model,
  (newValue) => {
    emit("update:modelValue", { ...newValue })
  },
  { deep: true },
)

defineExpose({
  validate,
  model,
})
</script>

<style scoped lang="sass">
.text-error
  @apply text-red-500 text-sm mt-1
</style>
