<template>
  <n-card class="protocol-stats-card">
    <!-- Stats Row -->
    <div class="grid grid-cols-4 gap-6">
      <div class="cursor-pointer" @click="showStargazersModal = true">
        <n-statistic :value="props.stars" class="stat-item">
          <template #label>
            <span class="stat-label">{{ $t("common.stars") }}</span>
          </template>
        </n-statistic>
      </div>
      <div :class="props.protocolId ? 'cursor-pointer' : undefined" @click="handleReusesClick">
        <n-statistic :value="props.reuseCount" class="stat-item">
          <template #label>
            <span class="stat-label">{{ $t("common.reuses") }}</span>
          </template>
        </n-statistic>
      </div>
      <n-statistic :value="props.downloadCount" class="stat-item">
        <template #label>
          <span class="stat-label">{{ $t("common.downloads") }}</span>
        </template>
      </n-statistic>
      <div :class="recordsClickable ? 'cursor-pointer' : undefined" @click="handleRecordsClick">
        <n-statistic :value="props.records" class="stat-item">
          <template #label>
            <span class="stat-label">{{ $t("common.records") }}</span>
          </template>
        </n-statistic>
      </div>
    </div>

    <!-- Weekly Downloads Chart -->
    <!-- <div class="mt-2 flex items-end justify-between pb-2">
      <div class="mr-2">
        <div class="whitespace-nowrap text-xs text-gray-500">
          Weekly Applied
        </div>
        <div class="font-semibold">
          <n-number-animation
            :from="0"
            :to="weeklyDownloads[weeklyDownloads.length - 1]"
            :duration="1500"
          />
        </div>
      </div>
      <div class="h-[40px] w-[120px] flex-none lg:w-[180px] md:w-[160px] sm:w-[140px]">
        <line-chart
          :data="chartData"
          :options="chartOptions"
        />
      </div>
    </div> -->

    <!-- Divider -->
    <n-divider class="!my-4" />

    <!-- Info Section -->
    <div class="flex items-center justify-between">
      <div class="flex flex-col items-center gap-2">
        <span class="text-gray-600">{{ $t("common.version") }}</span>
        <n-tag type="success" round>
          v{{ version }}
        </n-tag>
      </div>
      <div class="flex flex-col items-center gap-2">
        <span class="text-gray-600">{{ $t("common.lastUpdated") }}</span>
        <n-tooltip trigger="hover">
          <template #trigger>
            <n-time :time="dayjs(lastUpdated).valueOf()" type="relative" class="text-lg font-semibold" />
          </template>
          {{ formatDate(lastUpdated) }}
        </n-tooltip>
      </div>
      <div class="flex flex-col items-center gap-1">
        <span class="text-gray-600">{{ $t("common.license") }}</span>
        <span class="text-lg font-semibold">{{ license || $t("common.none") }}</span>
      </div>
    </div>
    <stargazers-modal
      v-if="props.protocolId"
      v-model:show="showStargazersModal"
      :protocol-id="props.protocolId"
    />
    <reusers-modal
      v-if="props.protocolId"
      v-model:show="showReusesModal"
      :protocol-id="props.protocolId"
    />
  </n-card>
</template>

<script setup lang="ts">
import { $t } from "@airalogy/shared/locales"
import { formatDate as formatDateBase } from "@airalogy/shared/utils"
import dayjs from "dayjs"
import relativeTime from "dayjs/plugin/relativeTime"
import { ref } from "vue"
import ReusersModal from "./reusers-modal.vue"
import StargazersModal from "./stargazers-modal.vue"
// import { Line as LineChart } from "vue-chartjs"

const props = withDefaults(defineProps<Props>(), {
  downloadCount: 0,
  stars: 0,
  reuseCount: 0,
  records: 0,
  version: "",
  license: "",
  protocolId: "",
  recordsClickable: false,
})

const emit = defineEmits<{
  (e: "recordsClick"): void
}>()

const showStargazersModal = ref(false)
const showReusesModal = ref(false)

// Enable relative time formatting
dayjs.extend(relativeTime)

// // Register ChartJS components
// ChartJS.register(
//   CategoryScale,
//   LinearScale,
//   PointElement,
//   LineElement,
//   Title,
//   Tooltip,
//   Filler,
// )

interface Props {
  downloadCount: number
  stars: number
  reuseCount: number
  records: number
  version: string
  license: string | null
  lastUpdated: string
  createdAt: string
  protocolId: string
  recordsClickable?: boolean
}

function handleRecordsClick() {
  if (!props.recordsClickable)
    return
  emit("recordsClick")
}

function handleReusesClick() {
  if (!props.protocolId)
    return
  showReusesModal.value = true
}

// Chart data and options are kept for potential future use
// const chartData = computed<ChartData<"line">>(() => ({
//   labels: Array.from({ length: props.weeklyDownloads.length }).fill(""),
//   datasets: [
//     {
//       data: props.weeklyDownloads,
//       fill: true,
//       borderColor: "#1A79FF",
//       backgroundColor: "rgba(26, 121, 255, 0.08)",
//       tension: 0.4,
//       borderWidth: 1.5,
//       pointRadius: 0,
//     },
//   ],
// }))

// const chartOptions = computed<ChartOptions<"line">>(() => ({
//   responsive: true,
//   maintainAspectRatio: false,
//   plugins: {
//     legend: {
//       display: false,
//     },
//     tooltip: {
//       enabled: true,
//       mode: "index",
//       intersect: false,
//       backgroundColor: "rgba(0, 0, 0, 0.7)",
//       padding: 4,
//       titleFont: {
//         size: 11,
//       },
//       bodyFont: {
//         size: 11,
//       },
//       callbacks: {
//         label: context => `${formatNumber(context.raw as number)}`,
//       },
//     },
//   },
//   scales: {
//     x: {
//       display: false,
//       grid: {
//         display: false,
//       },
//     },
//     y: {
//       display: false,
//       grid: {
//         display: false,
//       },
//       beginAtZero: true,
//     },
//   },
//   interaction: {
//     intersect: false,
//     mode: "index",
//   },
//   elements: {
//     point: {
//       radius: 0,
//       hoverRadius: 3,
//       backgroundColor: "#1A79FF",
//     },
//     line: {
//       tension: 0.3,
//     },
//   },
// }))

function formatDate(date: string) {
  return formatDateBase(date, "date-time-minute")
}
</script>

<style scoped lang="sass">
.stat-item
  @apply text-center transition-all duration-200 hover:scale-105

.stat-label
  @apply text-sm text-gray-600 whitespace-nowrap
</style>
