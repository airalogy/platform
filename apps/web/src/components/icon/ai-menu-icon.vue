<template>
  <n-icon size="40" class="transition">
    <svg width="40" height="40" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect
        x=".5"
        y=".5"
        width="39"
        height="39"
        rx="3.5"
        :fill="props.selected ? '#2B2B38' : 'transparent'"
        :stroke="props.selected ? '#2B2B38' : '#EAECF0'"
      />
      <path
        d="M29 19.5V23C29 23.5304 28.7893 24.0391 28.4142 24.4142C28.0391 24.7893 27.5304 25 27 25H19L14.5 29V25H13C11.8954 25 11 24.1046 11 23V13C11 12.4696 11.2107 11.9609 11.5858 11.5858C11.9609 11.2107 12.4696 11 13 11H16.5"
        :stroke="stroke" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
      />
      <path
        d="M25.775 15.7521C26.0171 16.3349 25.5888 16.9765 24.9578 16.9765C24.5948 16.9765 24.2686 16.7548 24.135 16.4172L23.7985 15.567H21.0193L20.7005 16.4189C20.575 16.7542 20.2545 16.9765 19.8964 16.9765C19.2829 16.9765 18.8674 16.3516 19.1048 15.7858L21.3605 10.41C21.5163 10.0385 21.8798 9.79688 22.2826 9.79688H22.634C23.0381 9.79688 23.4025 10.0401 23.5575 10.4133L25.775 15.7521ZM22.4292 11.7135L21.5163 14.1777H23.3218L22.4292 11.7135Z"
        :fill="stroke"
      />
      <path
        d="M28.6262 16.1042C28.6262 16.5859 28.2357 16.9765 27.7539 16.9765C27.2721 16.9765 26.8816 16.5859 26.8816 16.1042V10.6887C26.8816 10.1962 27.2809 9.79688 27.7734 9.79688C28.2444 9.79688 28.6262 10.1787 28.6262 10.6497V10.7903V16.1042Z"
        :fill="stroke"
      />
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

<style scoped lang="sass">
</style>
