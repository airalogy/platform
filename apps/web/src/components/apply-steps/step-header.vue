<template>
  <div>
    <div class="flex items-center gap-2">
      <n-icon
        size="20"
        class="flex items-center justify-center rounded-full"
        :class="[hasSelected ? 'text-primary' : 'text-[var(--text-2)]']"
      >
        <icon-ion-checkmark v-if="hasSelected" />
        <span v-else class="text-sm font-medium">{{ step }}</span>
      </n-icon>
      <div class="flex items-center gap-2 whitespace-nowrap">
        <span
          class="font-medium transition-colors duration-200"
          :class="[hasSelected ? 'text-primary' : 'text-[var(--text-2)]']"
        >{{ title }}</span>

        <n-button
          v-if="hasSelected && !disableCollapse && onReset"
          quaternary
          type="primary"
          size="tiny"
          class="ml-1"
          @click="onReset"
        >
          <template #icon>
            <n-icon>
              <icon-ion-create-outline />
            </n-icon>
          </template>
        </n-button>
      </div>
    </div>

    <n-collapse-transition :show="hasSelected && !disableCollapse">
      <slot name="selected" />
    </n-collapse-transition>
    <slot v-if="disableCollapse" name="content" />
    <n-collapse-transition v-else :show="!hasSelected">
      <slot v-if="$slots.default" />
      <n-form-item
        v-else
        :path="path"
        required
        class="mb-0"
        :show-label="false"
      >
        <slot name="content" />
      </n-form-item>
      <slot name="extra" />
    </n-collapse-transition>
  </div>
</template>

<script setup lang="ts">
interface Props {
  step: number
  title: string
  hasSelected?: boolean
  disableCollapse?: boolean
  onReset?: () => void
  path?: string
}

withDefaults(defineProps<Props>(), {
  hasSelected: false,
  disableCollapse: false,
})
</script>
