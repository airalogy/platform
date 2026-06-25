<template>
  <component
    v-bind="props.componentProps"
    :is="props.is"
    v-if="props.is"
    class="max-h-full w-full"
    :loading="isLoading"
  >
    <template v-if="props.assigner || props.dependent" #[props.assignerIconSlot]>
      <template v-if="props.assigner">
        <icon-local-cloud-done v-if="isLoading === false" />
        <icon-mdi-cloud-cancel-outline v-else color="var(--n-text-color-disabled)" />
      </template>
      <template v-else>
        <icon-local-cloud-upload />
      </template>
      <slot name="icon" />
    </template><slot />
  </component>
  <div v-else>
    {{ props.type }} not supported
  </div>
</template>

<script setup lang="ts">
import type { Component } from "vue"
import type { InputPropsOptions } from "../../types/input-props"
import { useProtocolFormInject } from "../../composables/useProtocolForm"

interface Props extends InputPropsOptions {
  is: Component
  componentProps: any
  assignerIconSlot?: string
}
const props = withDefaults(defineProps<Props>(), {
  assignerIconSlot: "suffix",
})

const { assignerLoadingRecord } = useProtocolFormInject()!

const isLoading = computed(() => assignerLoadingRecord.value[props.prop])
</script>
