<template>
  <n-modal
    :show="show"
    preset="card"
    :title="$t('page.hub.uploadModal.title')"
    :bordered="false"
    size="huge"
    class="w-160"
    :mask-closable="false"
    @update:show="handleUpdateShow"
  >
    <n-form ref="formRef" :model="model" :rules="rules" size="large">
      <n-form-item :label="$t('page.hub.uploadModal.protocolNameLabel')" path="name">
        <n-input
          v-model:value="model.name"
          type="text"
          :maxlength="30"
          required
          :placeholder="$t('page.hub.uploadModal.protocolNamePlaceholder')"
        />
      </n-form-item>

      <n-form-item :label="$t('page.hub.uploadModal.protocolFileLabel')" path="file" required>
        <n-upload
          v-model:file-list="model.fileList"
          :max="1"
          accept=".json,.yaml,.yml"
          @change="handleUploadChange"
        >
          <n-button>{{ $t("common.selectFile") }}</n-button>
        </n-upload>
      </n-form-item>

      <n-form-item :label="$t('common.version')" required>
        <n-input-group>
          <n-input-number
            v-model:value="model.version.major"
            :min="0"
            class="w-24"
            :placeholder="$t('common.major')"
          />
          <n-input-group-label>.</n-input-group-label>
          <n-input-number
            v-model:value="model.version.minor"
            :min="0"
            class="w-24"
            :placeholder="$t('common.minor')"
          />
          <n-input-group-label>.</n-input-group-label>
          <n-input-number
            v-model:value="model.version.patch"
            :min="0"
            class="w-24"
            :placeholder="$t('common.patch')"
          />
        </n-input-group>
      </n-form-item>
    </n-form>

    <div class="flex items-center justify-end">
      <n-button size="medium" class="mr-4" :disabled="loading" @click="handleCancel">
        {{ $t("common.cancel") }}
      </n-button>
      <n-button
        size="medium"
        type="primary"
        :disabled="loading"
        :loading="loading"
        @click="handleConfirm"
      >
        {{ $t("common.upload") }}
      </n-button>
    </div>
  </n-modal>
</template>

<script setup lang="ts">
import type { UploadFileInfo } from "naive-ui"
import { useClosableMessage, useFormRules, useLoading, useNaiveForm } from "@/composables"
import { $t } from "@airalogy/shared/locales"
import { ref } from "vue"

interface Props {
  show: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  "update:show": [value: boolean]
  "upload:complete": [data: UploadProtocolData]
}>()

interface UploadProtocolData {
  name: string
  file: File
  version: string
}

interface FormModel {
  name: string
  fileList: UploadFileInfo[]
  version: {
    major: number
    minor: number
    patch: number
  }
}

const { defaultRequiredRule } = useFormRules()
const { formRef, validate } = useNaiveForm()
const message = useClosableMessage()

const rules = {
  name: [defaultRequiredRule],
  file: [defaultRequiredRule],
}

const model = ref<FormModel>({
  name: "",
  fileList: [],
  version: {
    major: 1,
    minor: 0,
    patch: 0,
  },
})

const { loading, startLoading, endLoading } = useLoading()

function handleUpdateShow(value: boolean) {
  emit("update:show", value)
}

function handleCancel() {
  emit("update:show", false)
}

function handleUploadChange(options: { file: UploadFileInfo, fileList: UploadFileInfo[] }) {
  console.log("File changed:", options)
}

async function handleConfirm() {
  try {
    await validate()
    startLoading()

    if (!model.value.fileList.length) {
      message.error($t("form.file.required"))
      return
    }

    const version = `${model.value.version.major}.${model.value.version.minor}.${model.value.version.patch}`
    const file = model.value.fileList[0].file as File

    emit("upload:complete", {
      name: model.value.name,
      file,
      version,
    })

    handleCancel()
  }
  catch (error) {
    message.error((error as Error).message)
  }
  finally {
    endLoading()
  }
}
</script>
