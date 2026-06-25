<template>
  <n-card
    :bordered="false"
    title="Forget Password"
    class="m-auto h-fit w-60% md:top-0 md:min-w-60%"
    header-class="form__title max-md:!px-5"
    content-class="max-md:!px-5"
    size="huge"
  >
    <forget-pwd />
  </n-card>
</template>

<script setup lang="ts">
import ForgetPwd from "./components/forget-pwd.vue"
</script>

<style scoped lang="sass">
:deep(.form__title)
  --n-title-font-size: 36px
  font-family: PingFang SC
  white-space: nowrap
</style>
