<template>
  <n-modal
    v-model:show="showModal" preset="card" :title="$t('editor.template.title')"
    class="max-w-160 w-90vw" content-class="max-h-80vh overflow-y-auto"
    :mask-closable="false" :closable="!loading" :close-on-esc="!loading"
  >
    <p class="mb-5 text-sm text-gray-600">
      {{ $t("editor.template.description") }}
    </p>
    <n-form :model="model" :disabled="loading" size="large">
      <n-form-item :label="$t('editor.template.name')" required>
        <n-input v-model:value="model.name" data-testid="template-name" maxlength="80" :placeholder="$t('editor.template.namePlaceholder')" />
      </n-form-item>
      <n-form-item :label="$t('editor.template.template')">
        <n-radio-group v-model:value="model.templateType" class="w-full">
          <n-space vertical :size="16">
            <div v-for="option in options" :key="option.value">
              <n-radio :value="option.value" :data-testid="`template-${option.value}`">
                {{ option.label }}
              </n-radio>
              <p class="ml-6 mt-1 text-sm text-gray-500">
                {{ option.description }}
              </p>
            </div>
          </n-space>
        </n-radio-group>
      </n-form-item>
    </n-form>
    <n-alert v-if="error" role="alert" type="error" class="mb-4">
      {{ error }}
    </n-alert>
    <div class="flex justify-end gap-3">
      <n-button :disabled="loading" @click="showModal = false">
        {{ $t("common.cancel") }}
      </n-button>
      <n-button type="primary" :loading="loading" :disabled="!model.name.trim()" data-testid="template-create-confirm" @click="handleConfirm">
        {{ $t("editor.template.create") }}
      </n-button>
    </div>
  </n-modal>
</template>

<script setup lang="ts">
import type { ProtocolTemplate } from "@airalogy/components/monaco-editor/store/uploadFileDataStore"
import { $t } from "@airalogy/shared/locales"
import { useI18n } from "vue-i18n"

const props = defineProps<{
  show: boolean
  createTemplate: (template: ProtocolTemplate) => Promise<void>
}>()
const emit = defineEmits<{ (e: "update:show", value: boolean): void }>()
const showModal = computed({ get: () => props.show, set: value => emit("update:show", value) })
const { locale } = useI18n()
const loading = ref(false)
const error = ref("")
const model = reactive({ name: $t("editor.template.defaultName"), templateType: "first-record" })
const options = computed(() => [
  { value: "first-record", label: $t("editor.template.practice"), description: $t("editor.template.practiceDescription") },
  { value: "basic", label: $t("editor.template.basic"), description: $t("editor.template.basicDescription") },
  { value: "empty", label: $t("editor.template.empty"), description: $t("editor.template.emptyDescription") },
])

async function handleConfirm() {
  if (loading.value || !model.name.trim())
    return
  loading.value = true
  error.value = ""
  try {
    await props.createTemplate({ type: model.templateType, name: model.name.trim(), version: "0.1.0", locale: locale.value })
    showModal.value = false
  }
  catch {
    error.value = $t("editor.template.failed")
  }
  finally {
    loading.value = false
  }
}
</script>
