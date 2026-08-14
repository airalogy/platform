<template>
  <div class="size-full space-y-3">
    <edit-profile />
    <change-settings />
    <api-key-settings />
    <system-info-settings />
  </div>
</template>

<script lang="ts" setup>
import ApiKeySettings from "./api-key-settings.vue"
import ChangeSettings from "./change-settings.vue"
import EditProfile from "./edit-profile.vue"
import SystemInfoSettings from "./system-info-settings.vue"
</script>

<style lang="sass" scoped></style>
