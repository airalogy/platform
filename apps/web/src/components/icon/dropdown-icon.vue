<template>
  <div class="transition-transform" :class="[props.expended && 'rotate-180']">
    <icon-local-dropdown-filled v-if="props.filled" />
    <icon-local-dropdown-outline v-else />
  </div>
</template>

<script setup lang="ts">
interface IProps {
  filled?: boolean
  expended?: boolean
}
const props = withDefaults(defineProps<IProps>(), {
  filled: false,
  expended: false,
})
</script>

<style scoped></style>
