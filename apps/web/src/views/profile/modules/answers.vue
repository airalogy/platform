<template>
  <div class="size-full">
    <define-wrapper-item v-slot="{ $slots, title, handleViewAll, contentClass }">
      <div class="mb-4">
        <div class="mb-4 flex items-center gap-2 text-lg font-medium">
          {{ title }}
          <n-button
            v-if="handleViewAll"
            quaternary
            icon-placement="right"
            size="small"
            class="ml-1"
            @click="handleViewAll"
          >
            View All
            <template #icon>
              <n-icon size="12">
                <icon-ion-ios-arrow-forward />
              </n-icon>
            </template>
          </n-button>
        </div>
        <n-card class="w-full" size="small" :content-class="contentClass || '!p-1' ">
          <component :is="$slots.default" />
        </n-card>
      </div>
    </define-wrapper-item>

    <div class="size-full" v-bind="$attrs">
      <wrapper-item title="My Answers" content-class="!p-4">
        <div v-if="isLoadingAnswers" class="flex justify-center py-4">
          <n-spin size="medium" />
        </div>

        <div v-else-if="userAnswers && userAnswers.length > 0" class="space-y-4">
          <comment-item
            v-for="answer in userAnswers"
            :key="answer.id"
            :answer="answer"
            :question-id="null"
            :has-permission="true"
          />
        </div>

        <n-empty v-else description="No answers found" />
      </wrapper-item>
    </div>
  </div>
</template>

<script lang="ts" setup>
import CommentItem from "@/components/common/comment-item.vue"
import { useAuthStore } from "@/store/modules/auth"
import { createReusableTemplate } from "@vueuse/core"
import { useProfileStore } from "../hooks/useProfileStore"

defineOptions({ name: "ProfileAnswers", inheritAttrs: false })

const [DefineWrapperItem, WrapperItem] = createReusableTemplate<{
  title: string
  handleViewAll?: () => void
  contentClass?: string
}>()

const {
  userInfo,
  userAnswers,
  isLoadingAnswers,
  fetchUserAnswersData,
} = useProfileStore()!

const authStore = useAuthStore()

const showPrivate = computed(() => {
  return authStore.userInfo.id === userInfo.value?.id
})

watch(
  () => userInfo.value?.id,
  async (id) => {
    if (id) {
      await fetchUserAnswersData(id)
    }
  },
  { immediate: true },
)
</script>

<style lang="sass" scoped></style>
