<template>
  <div v-if="list.length > 0">
    <div
      v-for="item in list"
      :key="item.id"
      class="mb-4 border rounded-md bg-white p-4 shadow"
    >
      <h3 class="text-lg font-semibold">
        <router-link
          :to="{
            name: 'protocol-record-report',
            params: {
              labUid: item.lab_uid,
              projectUid: item.project_uid,
              protocolUid: item.research_uid,
              recordId: item.id,
            },
          }"
          class="!hover:router-link"
        >
          {{ item.title }}
        </router-link>
      </h3>
      <div v-if="item.headline" class="mt-2 text-gray-600" v-html="item.headline" />
      <div class="mt-2 flex items-center text-gray-500">
        <n-avatar v-if="item.user" size="small" :src="item.user.avatar_url" class="mr-2" :theme-overrides="{ color: 'transparent' }" />
        <router-link
          :to="{ name: 'user-profile', params: { username: item.user.username } }"
          class="!hover:router-link"
        >
          {{ item.user.name }}
        </router-link>
        <n-tag size="small" class="ml-4 mr-2">
          {{ item.lab_uid }}
        </n-tag>
        <n-tag size="small">
          {{ item.project_uid }}
        </n-tag>
        <n-time class="ml-auto" :time="new Date(item.created_at)" type="relative" />
      </div>
    </div>
  </div>
  <n-empty v-else description="No records found" />
</template>

<script setup lang="ts">
defineProps<{
  list: Api.Search.RecordSearchItem[]
}>()
</script>
