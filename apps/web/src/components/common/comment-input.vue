<template>
  <div>
    <n-divider v-if="props.showDivider" class="!my-4" />
    <n-flex v-if="props.mode === 'simple'" align="center" justify="space-between" :wrap="false">
      <n-input
        v-model:value="content" :placeholder="placeholder" :theme-overrides="{
          color: 'white',
          heightMedium: '40px',
        }"
      />
      <n-button type="primary" @click="reply">
        {{ props.confirmText }}
      </n-button>
    </n-flex>
    <template v-else-if="props.mode === 'advanced'">
      <markdown-editor
        v-model:text="content"
        raw-result
        :placeholder="placeholder"
        :min-height="150"
        :max-height="400"
        :loading="loading"
        class="mt-3"
        :style="{ '--border-hover-color': 'var(--primary-color)', '--border-focus-color': 'var(--primary-color)' }"
        :post-add-attachments="postAddAttachments"
      />
      <custom-auth-button
        :label="props.confirmText"
        :round="false"
        type="primary"
        class="mt-3"
        :disabled="loading"
        :loading="loading"
        @action="reply"
      />
      <n-button v-if="props.showCancel" quaternary :disabled="loading" @click="emit('cancel')">
        Cancel
      </n-button>
    </template>
  </div>
</template>

<script lang="ts" setup>
import { postAddAttachments } from "@/service/api/attachments"
import { postAddAnswer } from "@/service/api/discussion"
import { MarkdownEditor } from "@airalogy/components"
import { useClosableMessage, useLoading } from "@airalogy/composables"

interface IProps {
  questionId: string | number | null
  answerId?: string | number
  placeholder?: string
  confirmText?: string
  showDivider?: boolean
  showCancel?: boolean
  mode?: "simple" | "advanced"
}

const props = withDefaults(defineProps<IProps>(), {
  placeholder: undefined,
  confirmText: "Confirm",
  showDivider: true,
  showCancel: true,
  mode: "simple",
})

const emit = defineEmits<IEmits>()

interface IEmits {
  (e: "replied:question", result: any): void
  (e: "replied:answer", result: any): void
  (e: "failed"): void
  (e: "cancel"): void
}

const message = useClosableMessage()

const content = ref("")
const { loading, startLoading, endLoading } = useLoading()

async function reply() {
  if (content.value.length === 0) {
    message.info("Comment cannot be empty")
    return
  }

  const { questionId, answerId } = props
  if (!questionId) {
    message.error("Question id is required")
    return
  }

  startLoading()

  try {
    const result = await postAddAnswer({
      questionId,
      answerId,
      content: content.value,
    })

    if (result) {
      if (answerId) {
        emit("replied:answer", result)
      }
      else {
        emit("replied:question", result)
      }
    }

    content.value = ""
  }
  catch (error) {
    emit("failed")
  }
  finally {
    endLoading()
  }
}
</script>
