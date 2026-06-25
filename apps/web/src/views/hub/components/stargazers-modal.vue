<template>
  <n-modal
    :show="show"
    preset="card"
    class="w-600px"
    title="Stargazers"
    @update:show="(value) => emit('update:show', value)"
  >
    <n-spin :show="loading">
      <div class="min-h-200px">
        <n-list v-if="stargazers.length > 0" hoverable clickable>
          <n-list-item v-for="user in stargazers" :key="user.id">
            <template #prefix>
              <n-avatar :src="user.avatar_url || '/images/avatar_default.svg'" :size="40" round object-fit="cover" />
            </template>
            <n-thing :title="user.name" />
          </n-list-item>
        </n-list>
        <n-empty v-else description="No one has starred this protocol yet." />
      </div>
      <div v-if="total > pageSize" class="mt-4 flex justify-end">
        <n-pagination
          v-model:page="page"
          :page-size="pageSize"
          :item-count="total"
          @update:page="fetchStargazers"
        />
      </div>
    </n-spin>
  </n-modal>
</template>

<script setup lang="ts">
import { getStarUsers, StarResourceType, type StarUser } from "@/service/api/star"
import { ref, watch } from "vue"

const props = defineProps<{
  protocolId: string
  show: boolean
}>()

const emit = defineEmits(["update:show"])

const stargazers = ref<StarUser[]>([])
const loading = ref(false)
const page = ref(1)
const pageSize = ref(10)
const total = ref(0)

async function fetchStargazers() {
  if (loading.value || !props.protocolId) {
    return
  }
  loading.value = true
  try {
    const response = await getStarUsers({
      resource_type: StarResourceType.Protocol,
      resource_id: props.protocolId,
      page: page.value,
      page_size: pageSize.value,
    })
    if (response) {
      stargazers.value = response.users
      total.value = response.total_count
    }
  }
  catch (error) {
    console.error("Failed to fetch stargazers:", error)
  }
  finally {
    loading.value = false
  }
}

watch(
  () => props.show,
  (newVal) => {
    if (newVal && stargazers.value.length === 0) {
      fetchStargazers()
    }
  },
)
</script>
