<template>
  <n-icon size="40">
    <svg width="40" height="40" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect
        x="0.5" y="0.5" width="39" height="39" rx="3.5"
        :fill="props.selected ? '#2B2B38' : '#FFF'"
        :stroke="props.selected ? '#2B2B38' : '#EAECF0'"
      />
      <rect x="10" y="10" width="20" height="20" rx="2" :stroke="stroke" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
      <path x="10" y="10" d="M23 15h-5v5m0 5v-5m0 0h5" :stroke="stroke" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
    </svg>
  </n-icon>
</template>

<script setup lang="ts">
interface IProps {
  selected: boolean
}

const props = withDefaults(defineProps<IProps>(), { selected: false })
const stroke = computed(() => props.selected ? "#FFF" : "#A1A4AF")
</script>

<style scoped></style>
