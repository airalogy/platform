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
      <wrapper-item title="All Questions" content-class="!p-4">
        <div v-if="isLoadingQuestions" class="flex justify-center py-4">
          <n-spin size="medium" />
        </div>

        <div v-else-if="userQuestions && userQuestions.length > 0" class="space-y-4">
          <discussion-list-item
            v-for="question in userQuestions"
            :key="question.id"
            :item="question"
            :navigate-params="{}"
          />
        </div>

        <n-empty v-else description="No questions found" />
      </wrapper-item>
    </div>
  </div>
</template>

<script lang="ts" setup>
import { useAuthStore } from "@/store/modules/auth"
import DiscussionListItem from "@/views/project-protocols/modules/discussion/components/discussion-list-item.vue"
import { createReusableTemplate } from "@vueuse/core"
import { useProfileStore } from "../hooks/useProfileStore"

defineOptions({ name: "ProfileQuestions", inheritAttrs: false })

const [DefineWrapperItem, WrapperItem] = createReusableTemplate<{
  title: string
  handleViewAll?: () => void
  contentClass?: string
}>()

const {
  userInfo,
  userQuestions,
  isLoadingQuestions,
  fetchUserQuestionsData,
} = useProfileStore()!

const authStore = useAuthStore()

const showPrivate = computed(() => {
  return authStore.userInfo.id === userInfo.value?.id
})

watch(
  () => userInfo.value?.id,
  async (id) => {
    if (id) {
      await fetchUserQuestionsData(id)
    }
  },
  { immediate: true },
)
</script>

<style lang="sass" scoped></style>
