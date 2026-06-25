<template>
  <div>
    <n-flex v-if="total > 0" align="center" justify="space-between" :wrap="false" class="mb-4 w-full">
      <h2 class="text-xl font-semibold">
        {{ total }} {{ total > 1 ? "Answers" : "Answer" }}
      </h2>
      <global-sort-selector
        v-model="sortOption"
        :options="sortOptions"
        @update:value="handleSortChange"
      />
    </n-flex>
    <!-- <template v-if="showInput">
      <comment-input
        :question-id="props.id"
        placeholder="Please be sure to answer the question. Provide details and share your research."
        confirm-text="Submit Post"
        @replied:question="onRepliedQuestion"
      />
      <n-divider />
    </template> -->

    <loading-result :result="commentPage">
      <template v-for="(comment, idx) in list" :key="idx">
        <comment-item
          :question-id="props.id"
          :answer="comment"
          :has-permission="comment.user_id === userInfo.id"
          @delete:answer="handleDeleteAnswer"
        />
        <n-divider />
      </template>

      <n-pagination
        v-if="currentPage > 1"
        v-model:page="currentPage"
        :page-count="total"
        :page-slot="7"
        class="mt-5"
      />
    </loading-result>

    <div v-if="authStore.isLogin">
      <n-h2>
        Your Answer
      </n-h2>
      <comment-input
        :show-divider="false"
        mode="advanced"
        :question-id="props.id"
        placeholder="Please be sure to answer the question. Provide details and share your research."
        confirm-text="Post Your Answer"
        :show-cancel="false"
        @replied:question="onRepliedQuestion"
      />
    </div>
  <!--
  <custom-auth-button label="Post Your Answer" :icon="Message" type="primary" @action="showInput = !showInput" /> -->
  </div>
</template>

<script lang="ts" setup>
import type { Result } from "./loading-result.vue"
import { getAnswers } from "@/service/api/discussion"
import { useClosableMessage, usePagination } from "@airalogy/composables"
import { useAuthStore } from "../../store/modules/auth"

interface IProps {
  id: string | number | null
}

const props = defineProps<IProps>()

const authStore = useAuthStore()
const { userInfo } = authStore

// const { loading, startLoading, endLoading } = useLoading()
const message = useClosableMessage()

const list = ref<Api.Discussion.AnswerItem[]>([])
const total = ref<number>(0)

// Sort options setup
const sortOption = ref<string>("upvotes")
const sortOptions = [
  { label: "Most upvotes", value: "upvotes" },
  { label: "Most bookmarks", value: "bookmarks" },
  { label: "Newest answer", value: "newest" },
  { label: "Last modified", value: "modified" },
]

const { currentPage, currentPageSize } = usePagination({
  options: { page: 1, pageSize: 10, total },
  fetchData: fetchAnswers,
})

async function fetchAnswers({
  currentPage: currPage,
  currentPageSize: currSize,
}: {
  currentPage: number
  currentPageSize: number
}) {
  const { id } = props

  if (!id) {
    message.error("Question id is required")
    return
  }

  const result = await getAnswers({
    questionId: id,
    page: currPage,
    pageSize: currSize,
    sortBy: sortOption.value, // Add sort parameter for when API supports it
  })

  if (result) {
    list.value = result.answers
    total.value = result.total_count
  }
}

function handleSortChange() {
  // Reset to page 1 when sort option changes
  currentPage.value = 1
  fetchAnswers({ currentPage: 1, currentPageSize: currentPageSize.value })
}

// const showInput = ref(false)

async function onRepliedQuestion(answer: Omit<Api.Discussion.AnswerItem, "user">) {
  // showInput.value = false

  message.success("Your answer has been posted successfully")

  if (currentPage.value === 1) {
    await fetchAnswers({ currentPage: 1, currentPageSize: currentPageSize.value })
  }
}

const commentPage = computed<Result<{ pageNumber: number, items: Api.Discussion.AnswerItem[] }>>(
  () => {
    return {
      ok: true,
      value: {
        pageNumber: currentPage.value,
        items: list.value,
      },
    }
  },
)

onMounted(async () => {
  await fetchAnswers({ currentPage: currentPage.value, currentPageSize: currentPageSize.value })
})

async function handleDeleteAnswer(answer: Api.Discussion.AnswerItem) {
  await fetchAnswers({ currentPage: currentPage.value, currentPageSize: currentPageSize.value })
}
</script>
