<template>
  <n-modal
    v-model:show="showModal"
    preset="card"
    title="Create Protocol from Template"
    :bordered="false"
    size="huge"
    class="w-160"
    :mask-closable="false"
  >
    <n-form :model="model" size="large">
      <n-form-item label="Protocol Name" path="name">
        <n-input
          v-model:value="model.name"
          type="text"
          maxlength="30"
          placeholder="Enter protocol name"
        />
      </n-form-item>

      <n-form-item label="Template" path="templateType">
        <n-radio-group v-model:value="model.templateType">
          <n-space>
            <n-radio value="basic" checked>
              Basic Template
              <template #description>
                <span class="text-xs text-gray-500">
                  A simple starter template with basic protocol structure
                </span>
              </template>
            </n-radio>
            <n-radio value="empty">
              Empty Project
              <template #description>
                <span class="text-xs text-gray-500">
                  Start with a blank project with no template files
                </span>
              </template>
            </n-radio>
          </n-space>
        </n-radio-group>
      </n-form-item>
    </n-form>

    <div class="flex items-center justify-end">
      <n-button
        size="medium"
        type="primary"
        :loading="loading"
        @click="handleConfirm"
      >
        Create Protocol
      </n-button>
    </div>
  </n-modal>
</template>

<script setup lang="ts">
import { useClosableMessage } from "@/composables"
import { NButton, NForm, NFormItem, NInput, NModal, NRadio, NRadioGroup, NSpace } from "naive-ui"
import { reactive, ref } from "vue"

const props = defineProps<{
  show: boolean
  projectId: string
}>()

const emit = defineEmits<{
  (e: "update:show", value: boolean): void
  (e: "create", template: {
    type: string
    name: string
    version: string
  }): void
}>()

const showModal = ref(props.show)
const loading = ref(false)
const message = useClosableMessage()

const model = reactive({
  name: "Default Protocol",
  templateType: "basic",
  version: {
    major: 0,
    minor: 1,
    patch: 0,
  },
})

function handleConfirm() {
  loading.value = true

  try {
    const version = `${model.version.major}.${model.version.minor}.${model.version.patch}`

    emit("create", {
      type: model.templateType,
      name: model.name,
      version,
    })

    emit("update:show", false)
  }
  catch (error) {
    message.error("Failed to create protocol template")
    console.error("Failed to create protocol template:", error)
  }
  finally {
    loading.value = false
  }
}

// Keep internal and external show state in sync
watch(() => props.show, (val) => {
  showModal.value = val
})

watch(() => showModal.value, (val) => {
  emit("update:show", val)
})
</script>
