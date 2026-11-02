<template>
  <div class="profile-settings size-full min-w-0 space-y-3">
    <edit-profile />
    <change-settings />
    <api-key-settings />
    <external-access-settings />
    <system-info-settings />
  </div>
</template>

<script lang="ts" setup>
import ApiKeySettings from "./api-key-settings.vue"
import ChangeSettings from "./change-settings.vue"
import EditProfile from "./edit-profile.vue"
import ExternalAccessSettings from "./external-access-settings.vue"
import SystemInfoSettings from "./system-info-settings.vue"
</script>

<style lang="sass" scoped>
@media (max-width: 639px)
  .profile-settings :deep(.n-list-item)
    flex-wrap: wrap
    gap: 8px
  .profile-settings :deep(.n-list-item__prefix)
    width: 100%
    margin: 0
  .profile-settings :deep(.n-list-item__main)
    min-width: 0
    width: 100%
  .profile-settings :deep(.n-input)
    max-width: 100%
</style>
