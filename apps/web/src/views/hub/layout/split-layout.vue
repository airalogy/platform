<template>
  <n-button
    v-if="isCollapsed"
    class="absolute top-1/2 z-1000 -left-10"
    quaternary
    @click="handleToggle"
  >
    <template #icon>
      <n-icon v-if="isCollapsed">
        <icon-local-menu-collapsed />
      </n-icon>
      <n-icon v-else>
        <icon-local-menu-expand />
      </n-icon>
    </template>
  </n-button>

  <n-split v-bind="{ ...splitProps, ...$attrs }" v-model:size="splitSize" class="pb-10" :resize-trigger-size="2">
    <template #1>
      <slot name="aside">
        <sticky-fill-wrapper
          :offset="54"
          class="h-full w-full"
          :class="{ invisible: isCollapsed }"
        >
          <h3 class="list__title ml-4 !text-6">
            {{ $t("chat.askAira") }}
          </h3>
          <n-button class="absolute top-0 z-1000 -left-9" quaternary @click="handleToggle">
            <template #icon>
              <n-icon v-if="isCollapsed">
                <icon-local-menu-collapsed />
              </n-icon>
              <n-icon v-else>
                <icon-local-menu-expand />
              </n-icon>
            </template>
          </n-button>
          <n-divider class="!my-2" />
          <chat-component
            v-model:role="role"
            v-model:full-screen="appStore.fullContent"
            v-model:could-change-role="couldChangeRole"
            v-model:collapsed="isCollapsed"
            v-model:docked="docked"
            class="h-full w-full"
            v-bind="chatProps"
            source="hub"
          />
        </sticky-fill-wrapper>
      </slot>
    </template>
    <template #2>
      <slot />
    </template>
    <template #resize-trigger>
      <div v-if="!isCollapsed" class="n-split__resize-trigger h-full w-full" />
    </template>
  </n-split>
</template>

<script setup lang="ts">
import type { IProps as ChatProps } from "@airalogy/components/chat/composables/useChatInfoStore"

import ChatComponent from "@/components/chat/index.vue"
import { useBoolean } from "@/composables"
import { useAppStore } from "@/store/modules/app"

defineOptions({ name: "HubSplitLayout", inheritAttrs: false })

const props = withDefaults(defineProps<IProps>(), {
  defaultSpiltSize: 0.35,
  chatProps: () => ({}),
})

const emits = defineEmits<Emits>()

interface IProps {
  defaultSpiltSize?: number
  chatProps?: ChatProps
}

interface Emits {
  (e: "update:splitSize", payload: string | number): void
  (e: "expand:sider"): void
}

const { bool: isCollapsed, setFalse: expand, toggle } = useBoolean(false)
const docked = ref(false)

const appStore = useAppStore()
const splitSize = ref(props.defaultSpiltSize)
const chatProps = computed(() => ({
  hubSearchDefault: true,
  ...props.chatProps,
}))

const role = ref<1 | 2>(1)
const couldChangeRole = ref<boolean>(true)

provide("chat-role", { role, couldChangeRole })

watch(
  () => splitSize.value,
  (val) => {
    if (isCollapsed.value && val > 0) {
      expand()
      docked.value = false
      emits("expand:sider")
    }
    emits("update:splitSize", val)
  },
)

watch(isCollapsed, (val) => {
  if (val) {
    splitSize.value = 0
  }
  else {
    splitSize.value = props.defaultSpiltSize
  }
})

const splitProps = computed(() => {
  if (isCollapsed.value) {
    return { min: 0, max: 1, defaultSize: 0 }
  }

  return { min: 0.35, max: 0.65, defaultSize: 0.35 }
})

function handleToggle() {
  if (isCollapsed.value) {
    splitSize.value = props.defaultSpiltSize
  }
  else {
    splitSize.value = 0
  }

  docked.value = false
  toggle()
}

defineExpose({
  splitSize,
})
</script>

<style scoped lang="sass">
@use "@styles/sass/list.sass" as *

:deep(.n-split-pane-2)
  padding-left: 20px
  min-height: 500px
  overflow: visible
</style>
