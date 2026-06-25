<template>
  <n-list-item :key="item.id" :data-id="item.id" class="discussion-item max-w-[750px]">
    <div class="content-section">
      <h3 class="title text-lg font-500">
        <router-link
          class="!hover:router-link"
          :to="{
            name: 'protocol-discussion-detail',
            params: { ...navigateParams, questionId: String(item.id) },
          }"
        >
          {{ item.title }}
        </router-link>
      </h3>
      <div class="content h-fit max-w-full overflow-hidden whitespace-pre-wrap">
        <n-ellipsis :line-clamp="2" :tooltip="false" class="max-w-full text-sm text-gray-500">
          {{ item.content }}
        </n-ellipsis>
      </div>
      <div v-if="item.tags && item.tags.length > 0" class="tags my-2 w-full flex flex-wrap gap-2">
        <span class="mr-2 text-gray-500">Tags:</span>
        <n-tag v-for="(tag, idx) in item.tags" :key="idx" :bordered="false" size="small" class="tag w-fit" :color="{ color: '#F6F7F8', textColor: '#616B78' }">
          {{ tag }}
        </n-tag>
      </div>
    </div>

    <div class="meta-section mt-2 flex flex-wrap items-center gap-x-2 gap-y-2">
      <n-tag :color="{ color: 'transparent', borderColor: 'rgb(var(--primary-color))', textColor: 'rgb(var(--primary-color))' }">
        Answers
        <span class="mx-1 inline-block">{{ formatNumber(item.answers_count || 0) }}</span>
      </n-tag>

      <span class="meta-item flex items-center gap-2">
        <n-icon :component="UpvoteIcon" :size="20" :color="item.starred ? '#0084E2' : '#A1A4AF'" />
        <span class="min-w-5">{{ formatNumber(item.upvotes_count || 0) }}</span>
      </span>

      <span class="meta-item flex items-center gap-2">
        <n-icon :component="StarIcon" :size="16" :color="item.starred ? '#0084E2' : '#A1A4AF'" />
        <span class="min-w-5">{{ formatNumber(item.stars_count || 0) }}</span>
      </span>

      <span class="time-info ml-auto text-gray-500">
        {{ item.updated_at === item.created_at ? "Asked at" : "Updated at" }}
        <n-time :time="dayjs(item.updated_at).toDate()" type="relative" />
      </span>
      <span v-if="item.user" class="user-info">
        by
        <router-link class="user-name ml-1 !hover:router-link" :to="{ name: 'user-profile', params: { username: item.user.username } }" @click.stop>
          {{ item.user.name }}
        </router-link>
      </span>
      <n-skeleton v-else width="10em" />
    </div>
  </n-list-item>
</template>

<script lang="ts" setup>
import type { ProtocolModels } from "@airalogy/shared/types"
import { useRouterPush } from "@/composables/useRouterPush"
import { formatNumber } from "@airalogy/shared"
import UpvoteIcon from "~icons/local/thumb-up"
import StarIcon from "~icons/tabler/star-filled"
import dayjs from "dayjs"

interface Props {
  item: Api.Discussion.QuestionItem
  project: Api.Project.MyProjectInfo
  lab: Api.Lab.LabInfo
  protocol: ProtocolModels.ProjectProtocolInfo
  navigateParams: Record<string, string>
}

const props = defineProps<Props>()
const { routerPushByKey } = useRouterPush()

function handleClickItem() {
  routerPushByKey("protocol-discussion-detail", {
    params: {
      ...props.navigateParams,
      questionId: String(props.item.id),
    } as Record<string, string>,
  })
}
</script>

<style scoped lang="sass">
.discussion-item
  border-radius: 8px
  transition: transform 0.2s, box-shadow 0.2s

.title
  margin-bottom: 8px

.content
  margin-bottom: 8px

.meta-section
  font-size: 12px
  color: #606B7D

  .meta-item
    display: flex
    align-items: center

.user-name
  font-weight: 500

:deep(.n-list-item__main)
  max-width: 100%

.tag
  border-radius: 4px
  padding: 2px 8px
</style>
