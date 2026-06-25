<template>
  <div
    class="absolute right-3 top-3 flex flex-row border-[0.5px] rounded bg-[#ffffff77] opacity-0 group-hover/node-image:opacity-100"
  >
    <template v-if="shouldMerge">
      <n-dropdown
        :options="dropdownOptions"
        placement="bottom-end"
        trigger="click"
        @select="handleActionSelect"
      >
        <div>
          <tooltip-button
            tooltip="Open Menu"
            :icon="MenuIcon"
            :button-props="{ quaternary: true, size: 'small' }"
            @click.prevent="isOpen = true"
          />
        </div>
      </n-dropdown>
    </template>
    <template v-else>
      <template v-for="item in filteredActions" :key="item.key">
        <tooltip-button
          :icon="item.icon"
          :tooltip="item.tooltip"
          :button-props="{ quaternary: true, size: 'small' }"
          @click="handleAction(item.key)"
        />
      </template>
    </template>
  </div>
</template>

<script setup lang="tsx">
import type { DropdownOption } from "naive-ui"
import TooltipButton from "@airalogy/components/tooltip-button.vue"
import CopyIcon from "~icons/tabler/clipboard-copy"
import DownloadIcon from "~icons/tabler/download"
import LinkIcon from "~icons/tabler/link"
import MenuIcon from "~icons/tabler/menu"

interface Props {
  shouldMerge?: boolean
  isLink?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  shouldMerge: false,
  isLink: false,
})
const emit = defineEmits<IEmits>()

interface IEmits {
  (e: ActionKey): void

}

const isOpen = ref(false)

type ActionKey = "download" | "copy" | "copyId" | "copyLink"

const actionItems = computed((): {
  key: ActionKey
  icon: Component
  tooltip: string
  isLink?: boolean
}[] => [
  {
    key: "download",
    icon: DownloadIcon,
    tooltip: "Download image",
  },
  props.isLink
    ? {
        key: "copyLink",
        icon: LinkIcon,
        tooltip: "Copy image link",
        isLink: true,
      }
    : {
        key: "copyId",
        icon: CopyIcon,
        tooltip: "Copy image id",
        isLink: true,
      },
])

const filteredActions = computed(() =>
  actionItems.value.filter(item => props.isLink || !item.isLink),
)

const dropdownOptions = computed<DropdownOption[]>(() =>
  filteredActions.value.map(item => ({
    key: item.key,
    icon: () => h(item.icon),
    label: item.tooltip,
  })),
)

function handleAction(key: ActionKey) {
  isOpen.value = false
  emit(key)
}

function handleActionSelect(option: DropdownOption) {
  const key = option.key as ActionKey
  isOpen.value = false
  emit(key)
}
</script>
