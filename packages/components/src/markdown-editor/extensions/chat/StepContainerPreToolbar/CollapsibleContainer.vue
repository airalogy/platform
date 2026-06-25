<template>
  <div class="relative overflow-hidden" :class="maxHeight">
    <slot />
    <template v-if="props.collapsible">
      <div
        v-if="isExpanded"
        class="group mt-2 flex cursor-pointer justify-center"
        @click="isExpanded = false"
      >
        <span title="Collapse to compact view">
          <chevron-down-icon class-name="text-lightgray group-hover:text-foreground h-4 w-4 rotate-180" />
        </span>
      </div>
      <div v-else class="from-editor absolute bottom-0 left-0 right-0 h-12 to-transparent bg-gradient-to-t">
        <div
          class="group h-full flex cursor-pointer items-end justify-center pb-2"
          @click="isExpanded = true"
        >
          <span title="Expand to show full content">
            <chevron-down-icon class-name="text-lightgray group-hover:text-foreground h-4 w-4" />
          </span>
        </div>
      </div>
    </template>
  </div>
</template>

<script lang='ts' setup>
import ChevronDownIcon from "~icons/ion/chevron-down"

interface CollapsibleContainerProps {
  maxHeight?: string
  collapsible?: boolean
}

const props = withDefaults(defineProps<CollapsibleContainerProps>(), {
  collapsible: true,
  maxHeight: "max-h-40",
})

const isExpanded = ref(false)
</script>
