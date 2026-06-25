<template>
  <define-comment-content-item is="div" v-slot="{ comment, type, permission, $slots }">
    <div v-if="comment.user" class="mb-2 flex items-center gap-2">
      <n-avatar
        :src="comment.user.avatar_url || '/images/avatar_default.svg'"
        :size="32"
        color="transparent"
        object-fit="cover"
        class="vertical-middle"
      />
      <global-member-item
        :item="comment.user"
        :is-compact="false"
        type="project"
        class="w-fit"
      />
    </div>
    <div class="relative pl-10">
      <markdown-editor
        :text="comment.content"
        :readonly="!editingState[comment.id]"
        :hide-menu="!editingState[comment.id]"
        :hide-border="!editingState[comment.id]"
        :toolbar="!editingState[comment.id]"
        raw-result
        :post-add-attachments="postAddAttachments"
        :resolve-file="getCachedAttachment"
        @update:text="handleUpdateText"
      />
      <div v-if="editingState[comment.id]" class="my-2 flex items-center gap-2">
        <tooltip-button :tooltip="`Save ${type}`" type="primary" :loading="loadingState[`save-${comment.id}`]" @click="handleSave(comment)">
          Save
        </tooltip-button>

        <tooltip-button :tooltip="`Save ${type}`" :loading="loadingState[`save-${comment.id}` ]" @click="handleCancelEdit(comment)">
          Cancel
        </tooltip-button>
      </div>

      <div v-if="!editingState[comment.id]" class="my-2 flex items-center gap-2">
        <n-button
          v-auth
          :primary="comment.upvoted"
          size="small"
          :type="comment.upvoted ? 'primary' : 'default'"
          :loading="loadingState[comment.id]"
          :theme-overrides="{
            colorHover: '#0084E2',
            textColor: comment.upvoted ? '#0084E2' : '#A1A4AF',
            textColorHover: 'white',
          }"
          @click="handleVote(type, comment)"
        >
          <template #icon>
            <n-icon :component="UpvoteIcon" :size="20" />
          </template>

          {{ comment.upvotes_count ? formatNumber(comment.upvotes_count) : "Upvote" }}
        </n-button>

        <!-- <n-button
          quaternary
          size="small"
          :theme-overrides="{
            colorHover: '#0084E2',
            textColor: hasStarred(comment) ? '#0084E2' : '#A1A4AF',
            textColorHover: 'white',
          }"
        >
          <template #icon>
            <n-icon :component="StarIcon" :size="18" :color="hasStarred(comment) ? '#0084E2' : '#A1A4AF'" />
          </template>

          {{ formatNumber(0) }}
        </n-button> -->

        <template v-if="type === 'answer'">
          <add-to-bookmarker-modal
            v-if="comment.id"
            type="answer"
            :starred="comment.starred"
            :trigger="formatNumber(comment.stars_count || 0)"
            tooltip="Add this answer to bookmarker"
            :button-props="{ size: 'small', quaternary: true, themeOverrides: { colorHover: '#0084E2' } }"
            :icon-props="{ size: 18, color: comment.starred ? '#E3B341' : '#A1A4AF' }"
            :answer-id="comment.id"
            @modal:add-to-bookmarker="handleAddedToBookmarker($event, comment)"
          />

          <n-button v-auth quaternary size="small" @click="handleAddComment(comment)">
            <template #icon>
              <n-icon :component="MessageIcon" :size="18" color="#A1A4AF" />
            </template>

            <template v-if="showComments && total">
              Hide comments
            </template>
            <template v-else>
              {{ total ? formatNumber(total) : "Add a comment" }}
            </template>
          </n-button>
        </template>

        <relative-time-tooltip
          :time="comment.created_at"
          :label="type === 'answer' ? 'Answered' : 'Commented'"
          trigger-class="ml-auto"
        />

        <action-items v-if="permission" :comment="comment" :type="type" :permission="permission" />
      </div>
      <!--
      <div v-else-if="type === 'comment' && !editingState[comment.id]" class="my-2 flex items-center gap-2">
        <relative-time-tooltip
          :time="comment.created_at"
          label="Posted"
        />

        <n-button quaternary size="small" class="ml-auto" :loading="loadingState[comment.id]" :disabled="loadingState[comment.id]" @click="handleVote(type, comment)">
          <template #icon>
            <n-icon :component="UpvoteIcon" :size="20" :color="comment.upvoted ? '#0084E2' : '#A1A4AF'" />
          </template>

          {{ formatNumber(comment.upvotes_count || 0) }}
        </n-button>

        <action-items v-if="permission" :comment="comment" :type="type" :permission="permission" />
      </div> -->
      <!-- <custom-auth-button
          v-else-if="reply"
          label="Add A Comment"
          :icon="Message"
          quaternary
          type="tertiary"
          size="tiny"
          class="mt-2"
          @action="showInput = !showInput"
        /> -->
      <component :is="$slots.default" v-if="$slots.default" />
    </div>
  </define-comment-content-item>

  <define-action-items v-slot="{ comment, type, permission }">
    <template v-if="permission">
      <tooltip-button
        quaternary
        :tooltip="`Edit ${type}`"
        :icon="EditIcon"
        :icon-props="{ size: 16, color: '#A2A4AF' }"
        class="size-8 p-0"
        @click="handleEdit(comment)"
      />
      <n-popconfirm :title="`Delete ${type}`" @positive-click="handleDelete(comment, type)">
        <template #trigger>
          <div>
            <tooltip-button
              quaternary
              :tooltip="`Delete ${type}`"
              :icon="DeleteIcon"
              :icon-props="{ size: 16, color: '#A2A4AF' }"
              class="size-8 p-0"
            />
          </div>
        </template>
        {{ `Are you sure you want to delete this ${type}?` }}
      </n-popconfirm>
    </template>
  </define-action-items>

  <n-spin :show="loadingState.delete">
    <comment-content-item :comment="answer" type="answer" :permission="props.hasPermission">
      <n-spin v-if="showComments" :show="loadingState.comment" class="border rounded-xl p-4">
        <h3 class="mb-3 text-4 font-semibold">
          {{ total }} {{ total > 1 ? "comments" : "comment" }}
        </h3>
        <template v-for="(replyComment, index) in list" :key="replyComment.id">
          <comment-content-item :comment="replyComment" type="comment" :reply="false" class="ml-8 mt-5" :parent="answer" :permission="replyComment.user_id === userInfo.id" />
          <n-divider v-if="index !== list.length - 1" class="!my-3" />
        </template>

        <n-pagination
          v-if="pageCount > 1"
          v-model:page="currentPage"
          :page-count="pageCount"
          :page-slot="7"
          class="justify-end"
        />

        <comment-input
          v-show="showReplyState[answer.id]"
          :question-id="props.questionId"
          :answer-id="answer.id"
          :placeholder="`Reply to ${props.answer.user?.name || answer.user_id}`"
          confirm-text="Reply"
          :show-divider="false"
          :class="[list?.length && 'mt-4']"
          @replied:answer="onRepliedAnswer()"
        />

        <n-button
          v-show="!showReplyState[answer.id]"
          v-auth
          class="ml-auto mt-3 text-text-secondary"
          text
          @click="showReplyState[answer.id] = true"
        >
          Add a comment
        </n-button>
      </n-spin>
    </comment-content-item>
  </n-spin>
</template>

<script lang="ts" setup>
import AddToBookmarkerModal, { type StarredFolder } from "@/components/common/add-to-bookmarker-modal.vue"
import RelativeTimeTooltip from "@/components/common/relative-time-tooltip.vue"

import { getCachedAttachment, postAddAttachments } from "@/service/api/attachments"
import {
  deleteAnswer,
  getAnswers,
  postCancelUpvoteAnswer,
  postUpvoteAnswer,
  putChangeAnswer,
} from "@/service/api/discussion"
import { useAuthStore } from "@/store/modules/auth"
import { MarkdownEditor } from "@airalogy/components"

import { useClosableMessage, useLoading, usePagination } from "@airalogy/composables"
import { formatNumber } from "@airalogy/shared"
import { createReusableTemplate } from "@vueuse/core"
import UpvoteIcon from "~icons/local/thumb-up"
import EditIcon from "~icons/tabler/edit"
import MessageIcon from "~icons/tabler/message-filled"
import DeleteIcon from "~icons/tabler/trash"
import { useDialog } from "naive-ui"

interface IProps {
  questionId: string | number | null
  answer: Api.Discussion.AnswerItem
  hasPermission: boolean
}

const props = defineProps<IProps>()

const emits = defineEmits<IEmits>()
const { loadingState, startTargetLoading, endTargetLoading } = useLoading(false, ["vote", "delete", "comment"])
const editingState = reactive<Record<string, boolean>>({})
const showReplyState = reactive<Record<string, boolean>>({})

interface IEmits {
  (e: "delete:answer", answer: Api.Discussion.AnswerItem): void
  (e: "upvote:answer", answer: Api.Discussion.AnswerItem): void
  (e: "cancel-upvote:answer", answer: Api.Discussion.AnswerItem): void
  (e: "delete:comment", comment: Api.Discussion.AnswerItem): void
  (e: "upvote:comment", comment: Api.Discussion.AnswerItem): void
  (e: "cancel-upvote:comment", comment: Api.Discussion.AnswerItem): void
}

const [DefineCommentContentItem, CommentContentItem] = createReusableTemplate<{
  comment: Api.Discussion.AnswerItem
  type: "answer" | "comment"
  parent?: Api.Discussion.AnswerItem | null
  permission: boolean
}>()

const [DefineActionItems, ActionItems] = createReusableTemplate<{
  comment: Api.Discussion.AnswerItem
  type: "answer" | "comment"
  parent?: Api.Discussion.AnswerItem | null
  permission: boolean
}>()

const message = useClosableMessage()

const { userInfo } = useAuthStore()

const answer = toRef(props, "answer")

const list = ref<Api.Discussion.AnswerItem[]>([])
const total = ref<number>(props.answer.comments_count)
const showComments = ref(props.answer.comments_count > 0)

const { currentPage, currentPageSize, pageCount } = usePagination({
  options: { page: 1, pageSize: 5, total, mutateRoute: false },
  fetchData: fetchComments,
})

async function fetchComments({
  currentPage: currPage,
  currentPageSize: currSize,
}: {
  currentPage: number
  currentPageSize: number
}) {
  const {
    questionId,
    answer: { id: answerId },
  } = props

  if (!questionId) {
    message.error("Question id is required")
    return
  }

  try {
    startTargetLoading("comment")

    const result = await getAnswers({
      questionId,
      answerId,
      page: currPage,
      pageSize: currSize,
    })

    if (result) {
      list.value = result.answers
      total.value = result.total_count
    }
  }
  catch (error) {
    console.error(error)
  }
  finally {
    endTargetLoading("comment")
  }
}

async function onRepliedAnswer() {
  showComments.value = true
  await fetchComments({ currentPage: currentPage.value, currentPageSize: currentPageSize.value })
}

async function handleVote(type: "answer" | "comment", item: Api.Discussion.AnswerItem) {
  const { id: answerId, upvoted } = item
  if (!answerId) {
    message.error("Answer id is required")
    return
  }

  try {
    let result: { upvotes_count: number } | null = null
    startTargetLoading(answerId)

    if (upvoted) {
      result = await postCancelUpvoteAnswer(answerId)
      if (type === "answer") {
        emits("cancel-upvote:answer", item)
      }
      else {
        emits("cancel-upvote:comment", item)
      }
    }
    else {
      result = await postUpvoteAnswer(answerId)
      if (type === "answer") {
        emits("upvote:answer", item)
      }
      else {
        emits("upvote:comment", item)
      }
    }

    if (result) {
      if (type === "answer") {
        answer.value.upvotes_count = result.upvotes_count
      }

      if (type === "comment") {
        const target = list.value.find(it => it.id === item.id)

        if (target) {
          target.upvotes_count = result.upvotes_count
        }
      }
      item.upvoted = !upvoted
      message.success(`${upvoted ? "Cancel upvote" : "Upvote"} ${type} success`)
    }
  }
  finally {
    endTargetLoading(answerId)
  }
}

async function handleDelete(answer: Api.Discussion.AnswerItem, type: "answer" | "comment") {
  const { id: answerId } = answer
  if (!answerId) {
    message.error(`${type} id is required`)
    return
  }

  startTargetLoading("delete")
  const result = await deleteAnswer(answerId)
  if (result) {
    message.success(`${type} deleted`)
    if (type === "answer") {
      emits("delete:answer", answer)
    }
    else {
      emits("delete:comment", answer)
      await fetchComments({ currentPage: currentPage.value, currentPageSize: currentPageSize.value })
    }
  }

  endTargetLoading("delete")
}

const dialog = useDialog()
const content = ref<string>("")

function handleUpdateText(val: string) {
  content.value = val
}

function resetContent(comment: Api.Discussion.AnswerItem) {
  editingState[comment.id] = false
  content.value = ""
}

function handleEdit(comment: Api.Discussion.AnswerItem) {
  editingState[comment.id] = true
  content.value = comment.content || ""
}

async function handleSave(comment: Api.Discussion.AnswerItem) {
  try {
    startTargetLoading(`save-${comment.id}`)
    const result = await putChangeAnswer({ id: comment.id, content: content.value })
    if (result) {
      message.success("Answer updated")
      comment.content = content.value
      resetContent(comment)
    }
  }
  finally {
    endTargetLoading(`save-${comment.id}`)
  }
}

function handleCancelEdit(comment: Api.Discussion.AnswerItem) {
  dialog.warning({
    title: "Cancel Editing",
    content: "Are you sure you want to cancel editing this question?",
    positiveText: "Confirm",
    negativeText: "Cancel",
    onPositiveClick: () => {
      resetContent(comment)
    },
  })
}

function handleAddComment(comment: Api.Discussion.AnswerItem) {
  const previousValue = showComments.value
  showComments.value = !previousValue

  if (!comment.comments_count && typeof showReplyState[comment.id] === "undefined") {
    showReplyState[comment.id] = true
  }
}

async function handleAddedToBookmarker(folders: StarredFolder[], comment: Api.Discussion.AnswerItem) {
  if (folders.length > 0) {
    comment.starred = true
    comment.stars_count = (comment.stars_count || 0) + 1
  }
  else {
    comment.starred = false
    comment.stars_count = Math.max((comment.stars_count || 0) - 1, 0)
  }
}

watch(showComments, (val) => {
  if (val) {
    currentPage.value = 1
  }
})

onMounted(async () => {
  await fetchComments({ currentPage: currentPage.value, currentPageSize: currentPageSize.value })
})
</script>
