<template>
  <div>
    <icon-local-add-circle />
  </div>
</template>

<script setup lang="ts">
interface IProps {
  size?: number
}

const props = withDefaults(defineProps<IProps>(), {
  size: 20,
})
</script>

<style scoped></style>
