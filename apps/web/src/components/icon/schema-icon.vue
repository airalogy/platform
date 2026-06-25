<template>
  <n-icon :size="30">
    <svg width="30" height="30" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path
        d="M16.416 6.583h-7a1.75 1.75 0 00-1.75 1.75v14a1.75 1.75 0 001.75 1.75h10.5a1.75 1.75 0 001.75-1.75v-10.5l-5.25-5.25z"
        stroke="currentColor"
        stroke-width="1.5"
        stroke-linecap="round"
        stroke-linejoin="round"
      />
      <path
        d="M16.416 6.583v5.25h5.25M18.166 16.209h-7M18.166 19.708h-7M12.916 12.708h-1.75"
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
