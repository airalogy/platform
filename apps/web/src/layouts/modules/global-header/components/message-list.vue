<template>
  <n-scrollbar class="max-h-360px">
    <n-list>
      <n-list-item
        v-for="(item, index) in displayList"
        :key="item.id"
        class="cursor-pointer hover:bg-#f6f6f6 !px-3"
        :class="item.isRead && 'opacity-30'"
        @click="handleRead(index)"
      >
        <template #prefix>
          <n-avatar round :size="40" class="mt-2" src="/images/logo.svg" />
        </template>
        <n-ellipsis class="block max-w-80">
          <router-link
            class="align-middle no-underline hover:router-link"
            to="/home"
          >
            {{ item.activity.user.username }}
          </router-link>
          <span class="ml-2 inline-block align-middle color-text-secondary font-400">{{
            item.activity.action
          }}</span>
          <div>
            <router-link
              :to="{
                name: 'lab-projects',
                params: {
                  labId: item.activity.lab.id,
                },
              }"
              class="inline-block align-middle font-normal hover:router-link"
            >
              {{ item.activity.lab.name }}
            </router-link>
            <span class="pointer-events-none mx-1 inline-block text-sm font-500 -mt-1">/</span>
            <router-link
              :to="{
                name: 'project-protocols',
                params: {
                  projectId: item.activity.project.id,
                  labId: item.activity.lab.id,
                },
              }"
              class="inline-block align-middle font-normal hover:router-link"
            >
              {{ item.activity.project.name }}
            </router-link>
          </div>
        </n-ellipsis>
        <template #suffix>
          <span class="whitespace-nowrap text-3 font-400">{{ item.timeAgo }} </span>
        </template>
      </n-list-item>
    </n-list>
  </n-scrollbar>
</template>

<script lang="ts" setup>
import { formatTimeAgo } from "@vueuse/core"
import dayjs from "dayjs"

defineOptions({ name: "MessageList" })

const props = withDefaults(defineProps<Props>(), {
  list: () => [],
})

const emit = defineEmits<Emits>()

interface Props {
  list?: Api.Message.MessageItem[]
}

interface Emits {
  (e: "read", val: number): void
}

const displayList = computed(() => {
  return props.list.map((item): Api.Message.MessageItem & { timeAgo: string } => ({
    ...item,
    timeAgo: formatTimeAgo(dayjs(item.createdAt).toDate()),
  }))
})
function handleRead(index: number) {
  emit("read", index)
}
</script>
