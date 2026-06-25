<template>
  <n-icon :size="30">
    <svg width="30" height="30" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path
        d="M14.133 8.067H8.067A1.733 1.733 0 006.333 9.8v12.134a1.733 1.733 0 001.734 1.733H20.2a1.733 1.733 0 001.733-1.733v-6.067"
        stroke="currentColor"
        stroke-width="1.5"
        stroke-linecap="round"
        stroke-linejoin="round"
      />
      <path
        d="M20.633 6.767a1.838 1.838 0 012.6 2.6L15 17.6l-3.467.867L12.4 15l8.233-8.233z"
        stroke="currentColor"
        stroke-width="1.5"
        stroke-linecap="round"
        stroke-linejoin="round"
      />
    </svg>
  </n-icon>
</template>

<script setup lang="ts">
interface IProps {
  color?: string
}
const props = withDefaults(defineProps<IProps>(), {
  color: "#A1A4AF",
})
</script>

<style scoped></style>
