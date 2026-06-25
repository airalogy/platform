<template>
  <div v-if="list.length > 0">
    <div
      v-for="item in list"
      :key="item.id"
      class="mb-4 border rounded-md bg-white p-4 shadow"
    >
      <h3 class="text-lg font-semibold">
        <router-link
          :to="{ name: 'protocol-discussion-detail', params: { labUid: item.lab_id, projectUid: item.project_id, protocolUid: item.id, questionId: item.id } }"
          class="!hover:router-link"
        >
          {{ item.title }}
        </router-link>
      </h3>
      <div v-if="item.headline" class="mt-2 text-gray-600" v-html="item.headline" />
      <div class="mt-2 flex flex-wrap items-center gap-2">
        <div v-for="tag in item.tags" :key="tag" class="mr-1">
          <n-tag size="small" type="info">
            {{ tag }}
          </n-tag>
        </div>
      </div>
      <div class="mt-2 flex items-center text-gray-500">
        <n-avatar v-if="item.user" size="small" :src="item.user.avatar_url" class="mr-2" color="transparent" />
        <router-link
          :to="{ name: 'user-profile', params: { username: item.user.username } }"
          class="!hover:router-link"
        >
          @{{ item.user.name }}
        </router-link>
        <n-divider vertical class="mx-2" />
        <n-icon size="14" class="mr-1">
          <icon-ion-eye-outline />
        </n-icon>
        {{ item.views_count }}
        <n-icon size="14" class="ml-3 mr-1">
          <icon-ion-chatbox-outline />
        </n-icon>
        {{ item.answers_count }}
        <n-time class="ml-auto" :time="new Date(item.created_at)" type="relative" />
      </div>
    </div>
  </div>
  <n-empty v-else description="No discussion found" />
</template>

<script setup lang="ts">
import IconIonChatboxOutline from "~icons/ion/chatbox-outline"
import IconIonEyeOutline from "~icons/ion/eye-outline"

defineProps<{
  list: Api.Search.DiscussionSearchItem[]
}>()
</script>
