<template>
  <div class="layout-content">
    <markdown-editor
      :html="question?.content || ''"
      :post-add-attachments="postAddAttachments"
      :resolve-file="getCachedAttachment"
    />
  </div>
</template>

<script lang="ts" setup>
import { getCachedAttachment, postAddAttachments } from "@/service/api/attachments"
import { useAuthStore } from "@/store/modules/auth"
import { MarkdownEditor } from "@airalogy/components"

interface IProps {
  id: string
  item?: Api.Discussion.CreateQuestionResponse
}

const props = defineProps<IProps>()
const { userInfo } = useAuthStore()
const question = ref<Api.Discussion.CreateQuestionResponse | null>(props.item || null)
</script>
