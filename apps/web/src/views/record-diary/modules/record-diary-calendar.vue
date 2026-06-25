<template>
  <section class="record-diary-calendar">
    <div class="mb-3 flex flex-wrap items-center justify-between gap-3">
      <div>
        <h3 class="m-0 text-base font-semibold">
          {{ $t("page.recordDiary.calendarTitle") }}
        </h3>
        <p class="m-0 mt-1 text-sm text-gray-500">
          {{ $t("page.recordDiary.calendarHint") }}
        </p>
      </div>
      <n-spin :show="loading" size="small" />
    </div>

    <n-alert v-if="truncated" type="warning" class="mb-3" :show-icon="false">
      {{ $t("page.recordDiary.calendarTruncated", { count: eventLimit }) }}
    </n-alert>

    <full-calendar ref="calendarRef" class="record-diary-calendar__view" :options="calendarOptions" />
  </section>
</template>

<script setup lang="ts">
import type { RecordDiaryEventItem, RecordDiarySubmitter } from "@/service/api/users"
import type { CalendarOptions, DatesSetArg, EventClickArg } from "@fullcalendar/core"
import type { DateClickArg } from "@fullcalendar/interaction"
import {
  fetchAccessibleRecordDiaryEvents,
  fetchUserRecordDiaryEvents,
} from "@/service/api/users"
import { useAppStore } from "@/store/modules/app"
import { $t } from "@airalogy/shared/locales"
import zhCnLocale from "@fullcalendar/core/locales/zh-cn"
import dayGridPlugin from "@fullcalendar/daygrid"
import interactionPlugin from "@fullcalendar/interaction"
import FullCalendar from "@fullcalendar/vue3"

interface Props {
  targetUserId?: string | number
  profileScope?: boolean
  labUid?: string
  projectUid?: string
  submitter?: RecordDiarySubmitter
  selectedDate?: string
}

defineOptions({ name: "RecordDiaryCalendar" })

const props = withDefaults(defineProps<Props>(), {
  targetUserId: "",
  profileScope: false,
  labUid: undefined,
  projectUid: undefined,
  submitter: "all",
  selectedDate: undefined,
})

const emit = defineEmits<{
  selectDate: [value: string]
  viewRecord: [value: RecordDiaryEventItem]
}>()

const appStore = useAppStore()
const calendarRef = ref<{
  getApi: () => {
    refetchEvents: () => void
    render: () => void
  }
} | null>(null)
const loading = ref(false)
const events = shallowRef<RecordDiaryEventItem[]>([])
const truncated = ref(false)
const eventLimit = 500
const visibleRange = ref<{ start: Date, end: Date }>()
let requestSerial = 0

const calendarLocale = computed(() => appStore.locale === "zh-CN" ? "zh-cn" : "en")
const queryKey = computed(() => [
  props.profileScope ? "profile" : "accessible",
  props.targetUserId || "anonymous",
  props.labUid || "all-labs",
  props.projectUid || "all-projects",
  props.submitter,
].join(":"))

function buildCalendarEvents() {
  return events.value.map(item => ({
    id: String(item.airalogy_record_id),
    title: getEventTitle(item),
    start: item.metadata.record_current_version_submission_time,
    extendedProps: { item },
  }))
}

const calendarEvents = computed(buildCalendarEvents)
type CalendarEventInput = ReturnType<typeof buildCalendarEvents>[number]

function getCalendarButtonText() {
  return {
    today: $t("page.recordDiary.calendarToday"),
    month: $t("page.recordDiary.calendarMonth"),
  }
}

function handleCalendarEvents(_info: unknown, successCallback: (events: CalendarEventInput[]) => void) {
  successCallback(calendarEvents.value)
}

const calendarOptions = reactive<CalendarOptions>({
  plugins: [dayGridPlugin, interactionPlugin],
  locales: [zhCnLocale],
  locale: calendarLocale.value,
  initialView: "dayGridMonth",
  headerToolbar: {
    left: "prev,next today",
    center: "title",
    right: "",
  },
  buttonText: getCalendarButtonText(),
  height: "auto",
  firstDay: 1,
  dayMaxEventRows: 4,
  events: handleCalendarEvents as CalendarOptions["events"],
  eventDisplay: "block",
  eventTimeFormat: {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  },
  nowIndicator: true,
  navLinks: true,
  datesSet: handleDatesSet,
  dateClick: handleDateClick,
  eventClick: handleEventClick,
  dayCellClassNames: arg => toDateKey(arg.date) === props.selectedDate ? ["record-diary-calendar__selected-day"] : [],
})

function toDateKey(date: Date) {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, "0")
  const day = String(date.getDate()).padStart(2, "0")
  return `${year}-${month}-${day}`
}

function toInclusiveEndDateKey(end: Date) {
  const inclusiveEnd = new Date(end)
  inclusiveEnd.setDate(inclusiveEnd.getDate() - 1)
  return toDateKey(inclusiveEnd)
}

function getEventTitle(item: RecordDiaryEventItem) {
  const submitter = item.user.name || item.user.username
  const lab = item.lab.name || item.lab.uid
  const project = item.project.name || item.project.uid
  const protocol = item.protocol.name || item.protocol.uid
  const context = [
    props.labUid ? undefined : lab,
    props.projectUid ? undefined : project,
    protocol,
  ].filter(Boolean).join(" / ")
  const recordNumber = item.metadata.record_num
  const record = typeof recordNumber === "number"
    ? $t("page.recordDiary.recordTitle", { number: recordNumber })
    : $t("page.recordDiary.recordFallback")

  return `${context} · ${submitter} · ${record}`
}

async function refetchCalendarEvents() {
  await nextTick()
  calendarRef.value?.getApi().refetchEvents()
}

async function loadEvents() {
  if (props.profileScope && !props.targetUserId) {
    events.value = []
    truncated.value = false
    await refetchCalendarEvents()
    return
  }

  if (!visibleRange.value) {
    return
  }

  const serial = ++requestSerial
  loading.value = true
  try {
    const payload = {
      labUid: props.labUid,
      projectUid: props.projectUid,
      submitter: props.submitter,
      dateFrom: toDateKey(visibleRange.value.start),
      dateTo: toInclusiveEndDateKey(visibleRange.value.end),
      limit: eventLimit,
    }
    const data = props.profileScope
      ? await fetchUserRecordDiaryEvents(props.targetUserId, payload, `record-diary-calendar:${serial}`)
      : await fetchAccessibleRecordDiaryEvents(payload, `record-diary-calendar:${serial}`)

    if (serial !== requestSerial) {
      return
    }

    events.value = data?.events || []
    truncated.value = Boolean(data?.truncated)
    await refetchCalendarEvents()
  }
  finally {
    if (serial === requestSerial) {
      loading.value = false
    }
  }
}

function handleDatesSet(arg: DatesSetArg) {
  const nextRange = {
    start: new Date(arg.start),
    end: new Date(arg.end),
  }
  const currentRange = visibleRange.value
  const hasRangeChanged = !currentRange
    || currentRange.start.getTime() !== nextRange.start.getTime()
    || currentRange.end.getTime() !== nextRange.end.getTime()

  visibleRange.value = nextRange

  if (hasRangeChanged) {
    void loadEvents()
  }
}

function handleDateClick(arg: DateClickArg) {
  emit("selectDate", toDateKey(arg.date))
}

function handleEventClick(arg: EventClickArg) {
  arg.jsEvent.preventDefault()
  const item = arg.event.extendedProps.item as RecordDiaryEventItem | undefined
  if (item) {
    emit("viewRecord", item)
  }
}

watch(queryKey, () => {
  void loadEvents()
})

watch(calendarLocale, (locale) => {
  calendarOptions.locale = locale
  calendarOptions.buttonText = getCalendarButtonText()
})

watch(() => props.selectedDate, () => {
  calendarRef.value?.getApi().render()
})
</script>

<style scoped lang="sass">
.record-diary-calendar
  min-width: 0
  max-width: 100%
  border: 1px solid #E5E7EB
  border-radius: 8px
  background: #FFFFFF
  padding: 16px

  &__view
    min-height: 520px

  :deep(.fc)
    min-width: 0
    --fc-border-color: #E5E7EB
    --fc-button-bg-color: #FFFFFF
    --fc-button-border-color: #CBD5E1
    --fc-button-text-color: #334155
    --fc-button-hover-bg-color: #F8FAFC
    --fc-button-hover-border-color: #94A3B8
    --fc-button-active-bg-color: #1A79FF
    --fc-button-active-border-color: #1A79FF
    --fc-event-bg-color: #1A79FF
    --fc-event-border-color: #1A79FF
    --fc-today-bg-color: rgba(26, 121, 255, 0.08)
    font-size: 13px

  :deep(.fc-toolbar)
    flex-wrap: wrap
    gap: 8px

  :deep(.fc-toolbar-title)
    font-size: 18px
    font-weight: 600

  :deep(.fc-button)
    border-radius: 6px
    box-shadow: none
    font-size: 13px

  :deep(.fc-event)
    cursor: pointer
    border-radius: 5px
    padding: 1px 3px

  :deep(.fc-daygrid-day.record-diary-calendar__selected-day)
    background: rgba(26, 121, 255, 0.05)
    box-shadow: inset 0 0 0 2px rgba(26, 121, 255, 0.35)

  :deep(.fc-list-event)
    cursor: pointer

@media (max-width: 640px)
  .record-diary-calendar
    padding: 12px

    :deep(.fc-header-toolbar)
      align-items: flex-start
      flex-direction: column

    :deep(.fc-toolbar-chunk)
      max-width: 100%

    :deep(.fc-toolbar-title)
      font-size: 16px
</style>
