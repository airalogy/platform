<template>
  <header
    class="sticky left-0 right-0 top-0 z-30 border-b bg-white/80 backdrop-blur"
  >
    <div class="relative h-14 min-w-0 flex items-center justify-between overflow-hidden">
      <h1
        class="flex-1 cursor-pointer select-none overflow-hidden text-ellipsis whitespace-nowrap px-4 pr-6"
        @dblclick="onScrollToTop"
      >
        {{ currentChatHistory?.title ?? "" }}
      </h1>
      <div class="flex items-center space-x-2">
        <n-button class="h-10 w-10 !p-0" @click="handleExport">
          <template #icon>
            <n-icon class="text-xl text-[#4f555e]">
              <download-icon />
            </n-icon>
          </template>
        </n-button>
        <n-button class="h-10 w-10 !p-0" @click="handleClear">
          <template #icon>
            <n-icon class="text-xl text-[#4f555e]">
              <delete-icon />
            </n-icon>
          </template>
        </n-button>
      </div>
    </div>
  </header>
</template>

<script lang="ts" setup>
import { useChatStore } from "@airalogy/components/chat/store"
import { computed, nextTick } from "vue"

interface Props {
  usingContext: boolean
}

interface Emit {
  (ev: "export"): void
  (ev: "handleClear"): void
}

defineProps<Props>()

const emit = defineEmits<Emit>()

const chatStore = useChatStore()

const currentChatHistory = computed(() => chatStore.getChatHistoryByCurrentActive)

async function onScrollToTop() {
  const scrollRef = document.querySelector("#scrollRef")
  if (scrollRef)
    await nextTick(() => (scrollRef.scrollTop = 0))
}

function handleExport() {
  emit("export")
}

function handleClear() {
  emit("handleClear")
}
</script>
