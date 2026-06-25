<template>
  <div v-if="list.length > 0">
    <div
      v-for="item in list"
      :key="item.id"
      class="mb-4 border rounded-md bg-white p-4 shadow"
    >
      <h3 class="text-lg font-semibold">
        <router-link
          :to="{ name: 'protocol-info', params: { labUid: item.lab_uid, projectUid: item.project_uid, protocolUid: item.uid } }"
          class="!hover:router-link"
        >
          {{ item.name }}
        </router-link>
      </h3>
      <div v-if="item.headline" class="mt-2 text-gray-600" v-html="item.headline" />
      <div class="mt-2 flex items-center text-gray-500">
        <n-tag size="small" class="mr-2">
          {{ item.lab_uid }}
        </n-tag>
        <n-tag size="small">
          {{ item.project_uid }}
        </n-tag>
        <n-time class="ml-auto" :time="new Date(item.created_at)" type="relative" />
      </div>
    </div>
  </div>
  <n-empty v-else description="No protocols found" />
</template>

<script setup lang="ts">
defineProps<{
  list: Api.Search.ProtocolSearchItem[]
}>()
</script>
