<template>
  <router-link
    :to="{ name: 'root' }"
    class="pl-4 font-[PingFang_SC] no-underline"
    :title="$t('page.about.introduction')"
  >
    <icon-local-logo-icon-monochrome v-if="props.monochrome && props.compact" width="32px" height="32px" />
    <icon-local-logo-monochrome v-else-if="props.monochrome" width="124px" height="32px" />
    <icon-local-logo v-else-if="props.compact" width="32px" height="32px" />
    <icon-local-logo-icon v-else width="124px" height="32px" />
    <slot name="title">
      <h4 v-if="props.showTitle" class="py-6 text-4 text-white font-normal">
        {{ $t("page.about.introduction") }}
      </h4>
    </slot>
  </router-link>
</template>

<script setup lang="ts">
import { $t } from "@airalogy/shared/locales"

interface IProps {
  compact?: boolean
  color?: string
  monochrome?: boolean
  showTitle?: boolean
}

const props = withDefaults(defineProps<IProps>(), {
  compact: false,
  color: "white",
  monochrome: false,
  showTitle: false,
})
</script>

<style scoped></style>
