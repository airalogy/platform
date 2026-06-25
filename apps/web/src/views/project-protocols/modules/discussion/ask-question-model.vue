<template>
  <n-button v-auth v-bind="props.buttonProps" @click.stop="showModal">
    <template v-if="props.showIcon" #icon>
      <add-circle-outline />
    </template>
    {{ props.trigger }}
  </n-button>
  <n-modal
    :show="isShown" preset="card" title="Ask question" :bordered="false" size="huge"
    class="w-80vw overflow-visible" :mask-closable="false" @update:show="handleSetShow"
  >
    <n-form ref="formRef" :model="model" :rules="rules" size="large" class="h-[calc(100%-80px)] overflow-visible">
      <n-form-item label="Title" path="title">
        <n-input
          v-model:value="model.title" type="text" :maxlength="120" required show-count
          placeholder="Describe the question or problem briefly."
        />
      </n-form-item>
      <n-form-item label="Description" path="content">
        <markdown-editor
          v-model:html="model.content" v-model:text="model.text" raw-result
          wrapper-class="!min-h-[calc(90vh-500px)] !max-h-[calc(90vh-300px)]"
          editor-class="!max-h-full"
          placeholder="Introduce the question or problem and expand on what you put in the title."
          :post-add-attachments="postAddAttachments"
          :resolve-file="getCachedAttachment"
        />
      </n-form-item>
      <n-form-item label="Tags" path="tags">
        <n-dynamic-tags v-model:value="model.tags" />
      </n-form-item>
    </n-form>
    <div class="flex items-center justify-end">
      <n-button size="medium" class="mr-4" :disabled="loading" @click="handleCancel">
        Cancel
      </n-button>
      <n-button size="medium" type="primary" :disabled="loading" :loading="loading" @click="handleConfirm">
        Confirm
      </n-button>
    </div>
  </n-modal>
</template>

<script setup lang="ts">
import { useFormRules, useLoading, useNaiveForm, useShowModal } from "@/composables"
import { getCachedAttachment, postAddAttachments } from "@/service/api/attachments"
import { postAddQuestion } from "@/service/api/discussion"
import { MarkdownEditor } from "@airalogy/components"
import AddCircleOutline from "~icons/ion/add-circle-outline"
import { type ButtonProps, NButton } from "naive-ui/es/button"

interface IProps {
  showIcon?: boolean
  buttonProps?: ButtonProps & { class?: string }
  compact?: boolean
  trigger?: string
  id: string
  labInfo?: Api.Lab.LabInfo | null
  groupInfo?: Api.Groups.MyGroupsInfo | null
}
const props = withDefaults(defineProps<IProps>(), {
  showIcon: true,
  trigger: "Ask Question",
  buttonProps: () => ({ type: "primary" }),
  compact: true,
  labInfo: null,
  groupInfo: null,
})

const emits = defineEmits<IEmits>()

interface FormModel {
  title: string
  content: string
  text: string
  tags: string[]
}

interface IEmits {
  (e: "modal:new-question", payload: Api.Discussion.CreateQuestionResponse): void
  (e: "modal:close"): void
  (e: "modal:open"): void
}
const { defaultRequiredRule } = useFormRules()
const { formRef, validate } = useNaiveForm()
const { isShown, showModal, hideModal, setModalStatus } = useShowModal()

const rules: Record<keyof FormModel, App.Global.FormRule[]> = {
  title: [defaultRequiredRule],
  content: [defaultRequiredRule],
  text: [defaultRequiredRule],
  tags: [],
}

const model = ref<FormModel>({
  title: "",
  content: "",
  text: "",
  tags: [],
})

const { loading, startLoading, endLoading } = useLoading()

function handleCancel() {
  hideModal()
}

function handleSetShow(val: boolean) {
  setModalStatus(val)
}

async function handleConfirm() {
  await validate()

  const nodeId = props.id
  if (!nodeId)
    return

  startLoading()
  try {
    const { title, text, tags } = model.value
    const result = await postAddQuestion({
      protocol_id: nodeId,
      title,
      content: text,
      tags,
    })
    if (result) {
      emits("modal:new-question", result)
      hideModal()
    }
    else {
      // NOPE
    }
  }
  finally {
    endLoading()
  }
}
</script>

<style scoped lang="sass">
:deep(.n-base-selection)
  --n-height: 40px!important
  --n-color: #F7F8F9!important
  border-radius: 8px
</style>
