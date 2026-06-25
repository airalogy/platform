<template>
  <n-card>
    <template #header>
      <span class="list__title ml-3.5 capitalize !text-2xl">API Key Settings</span>
    </template>
    <n-form ref="formRef" :show-label="false" :model="model" :show-require-mark="false">
      <n-list show-divider>
        <n-list-item>
          <template #prefix>
            <h4 class="w-40 text-4 color-text-secondary">
              API Key
            </h4>
          </template>
          <n-form-item path="apiKey" :show-feedback="false" :class="!isKeyVisible && 'w-fit'">
            <n-input
              :value="isKeyVisible ? model.apiKey : maskedApiKey"
              type="textarea"
              disabled
              autosize
              required
              :placeholder="$t('page.login.common.passwordPlaceholder')"
            />
          </n-form-item>
          <template #suffix>
            <div class="flex items-center gap-2">
              <n-button v-if="model.apiKey && isKeyVisible" quaternary @click="copyToClipboard">
                Copy
              </n-button>
              <n-button quaternary @click="toggleKeyVisibility">
                {{ isKeyVisible ? 'Hide' : 'Show' }}
              </n-button>
              <n-popconfirm @positive-click="handleSubmit">
                Are you sure you want to regenerate the API key?
                <template #trigger>
                  <n-button type="error" class="mr-2" :loading="loading">
                    Regenerate
                  </n-button>
                </template>
              </n-popconfirm>
            </div>
          </template>
        </n-list-item>
      </n-list>
    </n-form>
  </n-card>
</template>

<script setup lang="ts">
import { useLoading, useNaiveForm } from "@/composables"
import { getUserAPIKey, putGenerateAPIKey } from "@/service/api/auth"
import { useAuthStore } from "@/store/modules/auth"
import { useClosableMessage } from "@airalogy/composables"
import { copyToClip } from "@airalogy/shared/utils"
import { useDialog } from "naive-ui"

defineOptions({ name: "ApiKeySettings" })

const authStore = useAuthStore()

interface FormModel {
  apiKey: string
}

const model: FormModel = reactive({
  apiKey: "",
})

const isKeyVisible = ref(false)
const maskedApiKey = computed(() => {
  if (!model.apiKey)
    return ""
  return "•".repeat(Math.min(20, model.apiKey.length))
})

function toggleKeyVisibility() {
  isKeyVisible.value = !isKeyVisible.value
}

const message = useClosableMessage()
const dialog = useDialog()

const { formRef, validate } = useNaiveForm()
const { loading, startLoading, endLoading } = useLoading()

async function handleSubmit() {
  await validate()
  startLoading()
  try {
    const { data } = await putGenerateAPIKey()
    if (data) {
      model.apiKey = data.api_key
      message.success("API Key regenerated successfully")
    }
  }
  catch (e) {
    message.error((e as Error).message)
  }
  finally {
    endLoading()
  }
}

async function copyToClipboard() {
  await copyToClip(model.apiKey)
  message.success("Copied to clipboard")
}

onMounted(async () => {
  const { data } = await getUserAPIKey()
  if (data)
    model.apiKey = data.api_key
})
</script>

<style scoped lang="sass">
@use "@styles/sass/list.sass" as *
</style>
