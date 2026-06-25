<template>
  <span v-if="compliance.visible" class="inline-flex flex-wrap items-center justify-center gap-x-3 gap-y-1">
    <a
      v-if="compliance.icpRecordNumber"
      :href="compliance.icpRecordUrl"
      target="_blank"
      rel="noreferrer"
    >
      {{ compliance.icpRecordNumber }}
    </a>
    <a
      v-if="compliance.policeRecordNumber && compliance.policeRecordUrl"
      class="police-record"
      :href="compliance.policeRecordUrl"
      target="_blank"
      rel="noreferrer"
    >
      <img class="police-record__icon" :src="policeRecordIcon" alt="">
      {{ compliance.policeRecordNumber }}
    </a>
    <span v-else-if="compliance.policeRecordNumber" class="police-record">
      <img class="police-record__icon" :src="policeRecordIcon" alt="">
      {{ compliance.policeRecordNumber }}
    </span>
  </span>
</template>

<script setup lang="ts">
import { getChinaComplianceFooterConfig } from "@/utils/env"

defineOptions({ name: "ChinaComplianceFooter" })

const compliance = getChinaComplianceFooterConfig()
const policeRecordIcon = computed(() => compliance.policeRecordIconUrl || "/images/icp-security-badge.png")
</script>

<style scoped lang="sass">
a
  color: inherit
  text-decoration: none

  &:hover
    color: white

.police-record
  display: inline-flex
  align-items: center
  gap: 4px

.police-record__icon
  width: 16px
  height: 16px
  flex: 0 0 auto
</style>
