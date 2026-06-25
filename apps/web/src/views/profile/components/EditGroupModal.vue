<template>
  <n-button
    quaternary
    circle
    type="info"
    @click="showModal = true"
  >
    <template #icon>
      <n-icon>
        <edit-outline />
      </n-icon>
    </template>
  </n-button>

  <n-modal
    v-model:show="showModal"
    preset="dialog"
    title="Edit Group"
    positive-text="Save"
    negative-text="Cancel"
    @positive-click="handlePositiveClick"
    @negative-click="handleNegativeClick"
  >
    <n-form
      ref="formRef"
      :model="model"
      :rules="rules"
      label-placement="left"
      label-width="auto"
      require-mark-placement="right-hanging"
      size="medium"
    >
      <n-form-item label="Name" path="name">
        <n-input v-model:value="model.name" placeholder="Input group name" />
      </n-form-item>
      <!-- Add more form items as needed -->
    </n-form>
  </n-modal>
</template>

<script setup lang="ts">
import type { FormInst, FormRules } from "naive-ui"
import EditOutline from "~icons/ion/pencil-outline"
import { ref } from "vue"

const props = defineProps<{
  item: Api.Groups.GroupsInfo
}>()

const emits = defineEmits<{
  (e: "modal:edit-group"): void
}>()

const showModal = ref(false)
const formRef = ref<FormInst | null>(null)

const model = ref({
  name: props.item.name,
})

const rules: FormRules = {
  name: {
    required: true,
    message: "Please input group name",
    trigger: ["blur", "input"],
  },
}

async function handlePositiveClick() {
  await formRef.value?.validate()
  // Implement your edit logic here
  emits("modal:edit-group")
  showModal.value = false
}

function handleNegativeClick() {
  showModal.value = false
}
</script>
