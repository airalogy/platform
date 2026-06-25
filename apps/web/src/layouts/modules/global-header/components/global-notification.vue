<template>
  <n-popover
    v-model:show="isShown"
    class="overflow-hidden p-0"
    trigger="click"
    :show-arrow="false"
    placement="bottom-end"
    content-class="!p-0"
  >
    <template #trigger>
      <n-badge :value="count" :max="99" class="mr-6 cursor-pointer">
        <n-icon color="white" :size="24">
          <notifications-outline />
        </n-icon>
      </n-badge>
    </template>
    <template #header>
      <div class="flex items-center justify-between">
        <h3 class="text-4 font-400">
          All information
        </h3>
        <n-button ghost type="primary" @click="handleAllRead">
          All read
        </n-button>
      </div>
    </template>
    <n-spin :show="loading">
      <message-list :list="list" @read="handleRead" />
    </n-spin>
  </n-popover>
</template>

<script setup lang="ts">
import { useLoading, useShowModal } from "@/composables"
import NotificationsOutline from "~icons/ion/notifications-outline"
import MessageList from "./message-list.vue"

const list = ref<Api.Message.MessageItem[]>([])

const { isShown, hideModal, showModal } = useShowModal()
const { loading, startLoading, endLoading } = useLoading()

const count = computed(() => {
  return list.value.reduce((acc, { isRead }) => (isRead ? acc : acc + 1), 0)
})

function handleAllRead() {
  list.value = list.value.map(it => ({ ...it, isRead: true }))
}
async function fetchMessage() {
  startLoading()
  /*
  const { data, error } = await request<Api.GetResponse<Api.Message.MessageItem>>({
    url: "/messages",
  })

  if (data) {
    list.value = data.data
  } else {
    // NOPE
  }
  */
  setTimeout(() => endLoading(), 500)
}

function handleRead(idx: number) {
  const target = list.value[idx]
  if (target) {
    target.isRead = true
  }
}
onMounted(async () => {
  await fetchMessage()
})
</script>

<style scoped lang="sass"></style>
