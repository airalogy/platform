<template>
  <div>
    <slot v-if="props.prefix" />
    <span class="aimd-field">
      <span :class="`aimd-field__scope aimd-field__scope--${type}`">{{ type }}</span>
      <span class="aimd-field__name">
        <slot name="name" />
      </span>
    </span>
    <slot v-if="!props.prefix" />
  </div>
</template>

<script setup lang="ts">
const props = withDefaults(defineProps<{
  type: string
  prefix?: boolean
}>(), {
  prefix: false,
})
</script>
