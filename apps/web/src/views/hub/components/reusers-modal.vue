<template>
  <n-modal
    :show="show"
    preset="card"
    class="w-600px"
    title="Reuses"
    @update:show="(value) => emit('update:show', value)"
  >
    <n-spin :show="loading">
      <div class="min-h-200px">
        <n-list v-if="reuses.length > 0" hoverable clickable>
          <n-list-item v-for="reuse in reuses" :key="reuse.id">
            <template #prefix>
              <n-avatar :size="40" round color="#EEF2F7" :style="{ color: '#4B5563' }">
                {{ getAvatarLabel(reuse.user) }}
              </n-avatar>
            </template>
            <n-thing :title="reuse.user.name || reuse.user.username">
              <template #description>
                <div class="text-xs text-gray-500">
                  <span v-if="reuse.user.username">@{{ reuse.user.username }}</span>
                  <span v-if="reuse.project?.name"> · {{ reuse.project.name }}</span>
                  <span v-if="reuse.name"> · {{ reuse.name }}</span>
                </div>
              </template>
            </n-thing>
          </n-list-item>
        </n-list>
        <n-empty v-else description="No one has reused this protocol yet." />
      </div>
      <div v-if="total > pageSize" class="mt-4 flex justify-end">
        <n-pagination
          v-model:page="page"
          :page-size="pageSize"
          :item-count="total"
          @update:page="fetchReuses"
        />
      </div>
    </n-spin>
  </n-modal>
</template>

<script setup lang="ts">
import type { ProtocolReuseEntry } from "@/service/api/protocol"
import { getProtocolReuses } from "@/service/api/protocol"
import { ref, watch } from "vue"

const props = defineProps<{
  protocolId: string
  show: boolean
}>()

const emit = defineEmits(["update:show"])

const reuses = ref<ProtocolReuseEntry[]>([])
const loading = ref(false)
const page = ref(1)
const pageSize = ref(10)
const total = ref(0)

function getAvatarLabel(user: ProtocolReuseEntry["user"]) {
  const base = (user?.name || user?.username || "?").trim()
  if (!base) {
    return "?"
  }
  return base.slice(0, 2).toUpperCase()
}

async function fetchReuses() {
  if (loading.value || !props.protocolId) {
    return
  }
  loading.value = true
  try {
    const { data } = await getProtocolReuses({
      protocolId: props.protocolId,
      page: page.value,
      pageSize: pageSize.value,
    })
    if (data) {
      reuses.value = data.protocols
      total.value = data.total_count
    }
  }
  catch (error) {
    console.error("Failed to fetch protocol reuses:", error)
  }
  finally {
    loading.value = false
  }
}

watch(
  () => props.show,
  (newVal) => {
    if (newVal) {
      page.value = 1
      fetchReuses()
    }
  },
)
</script>
