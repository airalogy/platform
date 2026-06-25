<template>
  <section class="record-diary-heatmap">
    <div class="mb-3 flex flex-wrap items-center justify-between gap-3">
      <div>
        <h3 class="m-0 text-base font-semibold">
          {{ $t("page.recordDiary.heatmapTitle") }}
        </h3>
        <p class="m-0 mt-1 text-sm text-gray-500">
          {{ $t("page.recordDiary.heatmapHint") }}
        </p>
      </div>
      <n-spin :show="loading" size="small" />
    </div>
    <div class="record-diary-heatmap__scroll">
      <div :id="heatmapId" ref="heatmapRef" class="record-diary-heatmap__chart" />
    </div>
  </section>
</template>

<script setup lang="ts">
import type { RecordDiarySubmitter, RecordDiarySummaryItem } from "@/service/api/users"
import {
  fetchAccessibleRecordDiarySummary,
  fetchUserRecordDiarySummary,
} from "@/service/api/users"
import { $t } from "@airalogy/shared/locales"
import CalHeatmap from "cal-heatmap"
import "cal-heatmap/cal-heatmap.css"

interface Props {
  targetUserId?: string | number
  profileScope?: boolean
  labUid?: string
  projectUid?: string
  submitter?: RecordDiarySubmitter
  selectedDate?: string
}

defineOptions({ name: "RecordDiaryHeatmap" })

const props = withDefaults(defineProps<Props>(), {
  targetUserId: "",
  profileScope: false,
  labUid: undefined,
  projectUid: undefined,
  submitter: "all",
  selectedDate: undefined,
})

const emit = defineEmits<{
  "update:selectedDate": [value?: string]
}>()

const heatmapRef = ref<HTMLElement | null>(null)
const loading = ref(false)
const summary = shallowRef<RecordDiarySummaryItem[]>([])
let calendar: CalHeatmap | null = null
const heatmapId = `record-diary-heatmap-${Math.random().toString(36).slice(2)}`
let requestSerial = 0

const today = computed(() => new Date())
const heatmapStart = computed(() => new Date(today.value.getFullYear(), 0, 1))
const heatmapEnd = computed(() => today.value)

const queryKey = computed(() => [
  props.profileScope ? "profile" : "accessible",
  props.targetUserId || "anonymous",
  props.labUid || "all-labs",
  props.projectUid || "all-projects",
  props.submitter,
].join(":"))

function toDateKey(date: Date) {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, "0")
  const day = String(date.getDate()).padStart(2, "0")
  return `${year}-${month}-${day}`
}

function parseDateKey(value?: string) {
  if (!value) {
    return undefined
  }
  const [year, month, day] = value.split("-").map(Number)
  if (!year || !month || !day) {
    return undefined
  }
  return new Date(year, month - 1, day)
}

async function destroyCalendar() {
  if (!calendar) {
    return
  }

  await calendar.destroy()
  calendar = null
}

async function paintHeatmap() {
  if (!heatmapRef.value) {
    return
  }

  await destroyCalendar()
  heatmapRef.value.innerHTML = ""

  const nextCalendar = new CalHeatmap()
  const onCalendarEvent = nextCalendar.on as unknown as (
    name: string,
    callback: (_event: PointerEvent, timestamp: number, value: number | null) => void,
  ) => void
  onCalendarEvent("click", (_event, timestamp) => {
    emit("update:selectedDate", toDateKey(new Date(timestamp)))
  })
  calendar = nextCalendar

  await nextCalendar.paint({
    itemSelector: `#${heatmapId}`,
    range: 1,
    date: {
      start: heatmapStart.value,
      min: heatmapStart.value,
      max: heatmapEnd.value,
      highlight: props.selectedDate ? [parseDateKey(props.selectedDate)].filter(Boolean) as Date[] : [],
    },
    domain: {
      type: "year",
      gutter: 0,
      label: {
        text: "YYYY",
        textAlign: "start",
        position: "top",
      },
    },
    subDomain: {
      type: "day",
      width: 11,
      height: 11,
      gutter: 2,
      radius: 2,
    },
    data: {
      source: summary.value,
      x: "date",
      y: "count",
      groupY: "sum",
      defaultValue: 0,
    },
    scale: {
      color: {
        type: "threshold",
        range: ["#EBEDF0", "#C6E48B", "#7BC96F", "#239A3B", "#196127"],
        domain: [1, 3, 6, 10],
      },
    },
    animationDuration: 0,
  })
}

async function loadSummary() {
  if (props.profileScope && !props.targetUserId) {
    summary.value = []
    await paintHeatmap()
    return
  }

  const serial = ++requestSerial
  loading.value = true
  try {
    const payload = {
      labUid: props.labUid,
      projectUid: props.projectUid,
      dateFrom: toDateKey(heatmapStart.value),
      dateTo: toDateKey(heatmapEnd.value),
      submitter: props.submitter,
    }
    const data = props.profileScope
      ? await fetchUserRecordDiarySummary(props.targetUserId, payload, `record-diary-heatmap:${serial}`)
      : await fetchAccessibleRecordDiarySummary(payload, `record-diary-heatmap:${serial}`)

    if (serial !== requestSerial) {
      return
    }

    summary.value = data?.summary || []
  }
  catch {
    if (serial === requestSerial) {
      summary.value = []
    }
  }
  finally {
    if (serial === requestSerial) {
      loading.value = false
      await nextTick()
      await paintHeatmap()
    }
  }
}

watch(queryKey, () => {
  void loadSummary()
}, { immediate: true })

watch(() => props.selectedDate, () => {
  void paintHeatmap()
})

onBeforeUnmount(() => {
  void destroyCalendar()
})
</script>

<style scoped lang="sass">
.record-diary-heatmap
  min-width: 0
  max-width: 100%
  border: 1px solid #E5E7EB
  border-radius: 8px
  background: #FFFFFF
  padding: 16px

  &__scroll
    max-width: 100%
    overflow-x: auto
    padding-bottom: 4px

  &__chart
    min-width: 900px

  :deep(.ch-subdomain-bg)
    cursor: pointer

  :deep(.ch-subdomain-bg.highlight)
    stroke: #0F172A
    stroke-width: 2px
</style>
