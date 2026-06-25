<template>
  <div class="question-detail">
    <!-- Title -->
    <template v-if="isEditing">
      <n-form ref="formRef" :model="formData" :rules="formRules">
        <n-form-item label="Title" required path="title" label-class="text-lg font-bold">
          <n-input v-model:value="formData.title" class="mt-0" />
        </n-form-item>
      </n-form>
    </template>
    <template v-else>
      <n-h1 class="border-b border-gray-200/50 pb-4">
        {{ question.title }}
      </n-h1>
    </template>

    <!-- Content -->
    <markdown-editor
      v-model:text="formData.content"
      :readonly="!isEditing"
      raw-result
      :content-class="isEditing ? 'pb-2' : ''"
      :hide-menu="!isEditing"
      :hide-border="!isEditing"
      :post-add-attachments="postAddAttachments"
      :resolve-file="getCachedAttachment"
    />

    <!-- Edit Mode Controls -->
    <template v-if="isEditing">
      <n-form-item label="Tags:" label-placement="left" class="mt-4" :show-feedback="false">
        <n-dynamic-tags v-model:value="formData.tags" />
      </n-form-item>
      <n-flex class="mt-4">
        <custom-auth-button
          primary
          type="primary"
          :check-auth="checkPermission"
          label="Save"
          :loading="loading"
          :disabled="loading"
          @action="emit('save')"
        />
        <custom-auth-button
          quaternary
          :check-auth="checkPermission"
          :loading="loading"
          :disabled="loading"
          :confirm-props="{
            title: 'Cancel Editing',
            content: 'Are you sure you want to cancel editing this question?',
          }"
          label="Cancel"
          @action="emit('cancel')"
        />
      </n-flex>
    </template>

    <!-- View Mode Metadata -->
    <template v-else>
      <div v-if="Array.isArray(question.tags) && question.tags.length > 0" class="my-6">
        <span class="mr-2 text-gray-500">Tags:</span>
        <n-tag v-for="(tag, idx) in question.tags" :key="idx" :bordered="false" size="small" class="tag w-fit" :color="{ color: '#F6F7F8', textColor: '#616B78' }">
          {{ tag }}
        </n-tag>
      </div>
    </template>

    <!-- Question Metadata -->
    <n-flex class="mt-6 w-full text-sm" justify="flex-end" :size="8" align="center">
      <!-- Author Info -->
      <template v-if="question.user">
        <n-avatar
          :src="question.user.avatar_url || '/images/avatar_default.svg'"
          fallback-src="/images/avatar_default.svg"
          :size="32"
          color="transparent"
          object-fit="cover"
          class="vertical-middle"
        />
        <global-member-item
          :item="{ ...question.user, id: question.user_id! }"
          :is-compact="false"
          type="project"
          class="mr-auto w-fit"
        />
      </template>

      <!-- Question Stats -->
      <relative-time-tooltip v-if="question.created_at" :time="question.created_at" label="Asked" trigger-class="mr-1" />
      <relative-time-tooltip v-if="question.updated_at" :time="question.updated_at" label="Modified" trigger-class="mr-1" />
      <slot v-if="$slots.actions" name="actions" />
    </n-flex>
    <slot />
  </div>
</template>

<script lang="ts" setup>
import type { FormInst } from "naive-ui"
import RelativeTimeTooltip from "@/components/common/relative-time-tooltip.vue"
import { useFormRules } from "@/composables"
import { getCachedAttachment, postAddAttachments } from "@/service/api/attachments"
import { MarkdownEditor } from "@airalogy/components"

interface Props {
  question: Api.Discussion.QuestionItem
  form: {
    title: string
    content: string
    tags: string[]
    html: string
  }
  isEditing: boolean
  loading: boolean
  checkPermission: () => boolean
}

interface Emits {
  (e: "update:form", form: Props["form"]): void
  (e: "save"): void
  (e: "cancel"): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const formRef = ref<FormInst | null>(null)

// Create local form data that syncs with props
const formData = useVModel(props, "form", emit)

const { defaultRequiredRule } = useFormRules()
const formRules = {
  title: [defaultRequiredRule],
  content: [defaultRequiredRule],
  tags: [defaultRequiredRule],
}

defineExpose({
  formRef,
  formData,
})
</script>

<style scoped lang="sass">
.question-detail
  --border-color: 100 100 100
</style>
