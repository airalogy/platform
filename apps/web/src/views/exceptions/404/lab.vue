<template>
  <global-layout>
    <header class="pt-5">
      <global-breadcrumb />
    </header>
    <div class="flex-center flex-1">
      <n-icon :size="32">
        <icon-local-logo-icon />
      </n-icon>
      <h2 class="ml-4 !text-6">
        404 | LAB NOT FOUND
      </h2>
    </div>
  </global-layout>
</template>

<script setup lang="ts">
import GlobalLayout from "@/layouts/global-layout/index.vue"
</script>

<style scoped lang="sass"></style>
