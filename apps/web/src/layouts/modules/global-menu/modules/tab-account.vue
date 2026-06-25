<template>
  <div class="max-h-80 w-80">
    <global-search />
    <h1>{{ $t("page.profile.account") }}</h1>
  </div>
</template>

<script setup lang="ts">
import GlobalSearch from "@/layouts/modules/global-search/index.vue"
import { $t } from "@airalogy/shared/locales"
</script>

<style scoped lang="sass"></style>
