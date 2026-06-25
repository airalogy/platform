<template>
  <split-layout class="layout-content" content-class="px-4">
    <loading-result v-slot="{ value: question }" :result="result">
      <question-detail
        ref="formRef"
        v-model:form="form"
        :question="question"
        :is-editing="isEditing"
        :loading="loadingKeys.length > 0"
        :check-permission="checkPermission"
        @save="handleEditQuestion"
        @cancel="handleCancelEdit"
      >
        <!--  -->
        <template v-if="hasPermission" #actions>
          <tooltip-button
            quaternary
            tooltip="Edit Question"
            :icon="EditIcon"
            :icon-props="{ size: 16, color: '#A2A4AF' }"
            class="size-8 p-0"
            @click="handleStartEdit"
          />

          <n-popconfirm title="Delete Question" @positive-click="handleDelete">
            <template #trigger>
              <div>
                <tooltip-button
                  quaternary
                  tooltip="Delete Question"
                  :icon="DeleteIcon"
                  :icon-props="{ size: 16, color: '#A2A4AF' }"
                  class="size-8 p-0"
                />
              </div>
            </template>
            Are you sure you want to delete this question?
          </n-popconfirm>
        </template>
        <div class="mt-4 flex items-center gap-2">
          <tooltip-button
            v-auth
            :tooltip="question.upvoted ? 'Unvote Question' : 'Upvote Question'"
            :icon="UpvoteIcon"
            :icon-props="{ size: 20 }"
            :button-props="{
              type: question.upvoted ? 'primary' : 'default',
              size: 'small',
              themeOverrides: {
                colorHover: '#0084E2',
                textColor: question.upvoted ? '#0084E2' : '#A1A4AF',
                textColorHover: 'white',
              },
            }"
            :loading="loadingState.upvote"
            :disabled="loadingState.upvote"
            @click="handleUpvote"
          >
            {{ question.upvotes_count ? formatNumber(question.upvotes_count) : "Upvote" }}
          </tooltip-button>

          <add-to-bookmarker-modal
            type="question"
            :starred="question.starred"
            :trigger="formatNumber(question.stars_count || 0)"
            tooltip="Add this question to bookmarker"
            :button-props="{ size: 'small', quaternary: true, themeOverrides: { colorHover: '#0084E2' } }"
            :icon-props="{ size: 18, color: question.starred ? '#E3B341' : '#A1A4AF' }"
            :question-id="question.id"
            @modal:add-to-bookmarker="handleAddedToBookmarker(question)"
          />
        </div>
      </question-detail>
      <div class="my-5 b-px b-text-secondary opacity-10" />
      <question-answer-list :id="questionId" />
    </loading-result>
  </split-layout>
</template>

<script lang="ts" setup>
import type { Result } from "@/components/common/loading-result.vue"
import QuestionAnswerList from "@/components/common/question-answer-list.vue"
import { useLoading } from "@/composables"
import { useRouterPush } from "@/composables/useRouterPush"
import { deleteQuestion, getQuestionDetail, postCancelUpvoteQuestion, postUpvoteQuestion, putChangeQuestion } from "@/service/api/discussion"

import { request } from "@/service/request"

import { useAppStore } from "@/store/modules/app"
import { useAuthStore } from "@/store/modules/auth"
import SplitLayout from "@/views/project-protocols/layout/split-layout.vue"
import { useClosableMessage } from "@airalogy/composables"
import { formatNumber } from "@airalogy/shared"

import UpvoteIcon from "~icons/local/thumb-up"
import EditIcon from "~icons/tabler/edit"

import DeleteIcon from "~icons/tabler/trash"

import { nanoid } from "nanoid"
import QuestionDetail from "./components/question-detail.vue"

const { routerPushByKey } = useRouterPush()
const { reloadPage } = useAppStore()
const message = useClosableMessage()

const { userInfo } = useAuthStore()
const result = ref<Result<Api.Discussion.QuestionItem> | null>(null)

const route = useRoute()

const questionId = computed(() => (route.params.questionId as string) || null)

const { loadingState, startTargetLoading, endTargetLoading, loadingKeys } = useLoading(false, ["edit", "upvote", "star"])
// const author = ref<Api.Profile.User | null>(null)
const isEditing = ref(false)
const form = reactive<{ title: string, content: string, tags: string[], html: string }>({
  title: "",
  content: "",
  html: "",
  tags: [],
})

function checkPermission() {
  if (!result.value?.ok) {
    return false
  }
  const { user_id: creatorId } = result.value.value

  if (!userInfo.id || !creatorId) {
    return false
  }

  return userInfo.id === creatorId
}

const hasPermission = computed(() => {
  return checkPermission()
})

async function handleDelete() {
  if (!result.value?.ok) {
    return false
  }
  const { id, protocol_id: research_id } = result.value.value

  if (!id) {
    message.warning("Question uuid is required")
    return false
  }

  const success = await deleteQuestion(id)

  if (success) {
    message.success("Question deleted")
    if (research_id) {
      await routerPushByKey("protocol-discussions", { params: { protocolId: String(research_id) } })
    }
    else {
      await routerPushByKey("home")
    }

    return true
  }

  return false
}
const formRef = ref<InstanceType<typeof QuestionDetail> | null>(null)
function handleRestoreForm() {
  if (result.value?.ok) {
    const { title = "", content = "", tags } = result.value?.value || {}
    form.title = title
    form.content = content
    form.html = ""

    if (Array.isArray(tags)) {
      form.tags = tags.slice()
    }
    else {
      form.tags = []
    }
  }
}

function handleStartEdit() {
  handleRestoreForm()

  void nextTick(() => {
    isEditing.value = true
  })
}

function handleCancelEdit() {
  handleRestoreForm()

  void nextTick(() => {
    isEditing.value = false
  })
}

async function handleEditQuestion() {
  if (!questionId.value)
    return

  try {
    await formRef.value?.formRef?.validate()
    startTargetLoading("edit")
    const uuid = result.value?.ok ? result.value.value?.id : undefined
    if (!uuid) {
      message.error("Question uuid is required")
      return
    }

    const success = await putChangeQuestion({ uuid, ...form })

    if (success) {
      isEditing.value = false
      await reloadPage(50)
    }
  }
  catch (e: any) {
    message.error(e?.message || "Failed to edit question")
  }
  finally {
    endTargetLoading("edit")
  }
}

async function handleUpvote() {
  if (!questionId.value || !result.value?.ok) {
    return
  }

  const { upvoted } = result.value.value
  try {
    startTargetLoading("upvote")
    if (upvoted) {
      const res = await postCancelUpvoteQuestion(questionId.value)
      if (res) {
        result.value.value.upvotes_count = res.upvotes_count
      }
    }
    else {
      const res = await postUpvoteQuestion(questionId.value)
      if (res) {
        result.value.value.upvotes_count = res.upvotes_count
      }
    }

    result.value.value.upvoted = !upvoted
  }
  finally {
    endTargetLoading("upvote")
  }
}

async function handleAddedToBookmarker(question: Api.Discussion.QuestionItem) {
  if (!question.id) {
    return
  }

  const data = await getQuestionDetail(question.id, nanoid())
  if (data) {
    result.value = { ok: true, value: data }
  }
}

watchEffect(async (onCleanup) => {
  if (!questionId.value) {
    return
  }

  const requestId = nanoid()

  onCleanup(() => request.cancelRequest(requestId))
  const data = await getQuestionDetail(questionId.value, requestId)

  if (data) {
    result.value = { ok: true, value: data }
    const { title, content, tags } = data
    form.title = title || ""
    form.content = content || ""
    form.tags = tags || []
  }
})

// watchEffect(async () => {
//   if (!result.value?.ok) {
//     return
//   }

//   const { user_id } = result.value.value || {}

//   if (user_id) {
//     const user = await getUserInfoById(user_id)

//     author.value = user.data
//   }

//   handleRestoreForm()
// })
</script>
