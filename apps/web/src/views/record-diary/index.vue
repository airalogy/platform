<template>
  <loading-list-wrapper
    :key="requestKey"
    :fetcher="fetcher"
    :immediate="canFetch"
    :page-size="10"
    :page-sizes="[5, 10, 20, 50]"
    show-size-picker
    class="record-diary-page"
  >
    <template #header>
      <div class="mb-4 flex flex-col gap-3">
        <div class="record-diary-time-toolbar">
          <n-radio-group v-model:value="viewMode" size="small">
            <n-radio-button value="heatmap">
              {{ $t("page.recordDiary.heatmapTitle") }}
            </n-radio-button>
            <n-radio-button value="calendar">
              {{ $t("page.recordDiary.calendarTitle") }}
            </n-radio-button>
          </n-radio-group>
        </div>
        <record-diary-calendar
          v-if="viewMode === 'calendar'"
          :target-user-id="targetUserId"
          :profile-scope="isProfileScope"
          :lab-uid="effectiveLabUid"
          :project-uid="effectiveProjectUid"
          :submitter="submitterFilter"
          :selected-date="selectedDate"
          @select-date="setSelectedDate"
          @view-record="handleViewReport"
        />
        <record-diary-heatmap
          v-else
          v-model:selected-date="selectedDate"
          :target-user-id="targetUserId"
          :profile-scope="isProfileScope"
          :lab-uid="effectiveLabUid"
          :project-uid="effectiveProjectUid"
          :submitter="submitterFilter"
        />
        <div class="flex flex-wrap items-center justify-between gap-3">
          <n-tag v-if="selectedDate" type="info" closable @close="clearSelectedDate">
            {{ $t("page.recordDiary.selectedDate", { date: selectedDate }) }}
          </n-tag>
          <span v-else />
          <div class="flex flex-wrap items-center gap-3">
            <n-select
              v-if="showLabFilter"
              v-model:value="selectedLabUid"
              :options="labFilterOptions"
              :loading="labLoading"
              :placeholder="$t('page.recordDiary.labFilterPlaceholder')"
              size="small"
              class="record-diary-lab-filter"
            />
            <n-select
              v-if="showProjectFilter"
              v-model:value="selectedProjectUid"
              :options="projectFilterOptions"
              :loading="projectLoading"
              :placeholder="$t('page.recordDiary.projectFilterPlaceholder')"
              size="small"
              class="record-diary-project-filter"
            />
            <n-radio-group
              v-if="showSubmitterFilter"
              v-model:value="submitterFilter"
              size="small"
            >
              <n-radio-button
                v-for="option in submitterOptions"
                :key="option.value"
                :value="option.value"
              >
                {{ option.label }}
              </n-radio-button>
            </n-radio-group>
          </div>
        </div>
      </div>
    </template>

    <template #default="{ data }">
      <n-timeline size="large" class="record-diary-timeline">
        <n-timeline-item
          v-for="(item, index) in data"
          :key="item.airalogy_record_id"
          :time="formatDate(getSubmittedAt(item), 'date-time')"
        >
          <div v-if="shouldShowDate(data, index)" class="mb-3 text-sm text-gray-500 font-medium">
            {{ formatDate(getSubmittedAt(item), "date") }}
          </div>
          <article class="record-diary-card" :data-record-key="getRecordKey(item)">
            <header class="flex flex-wrap items-start justify-between gap-3">
              <div class="min-w-0">
                <div class="mb-1 flex flex-wrap items-center gap-2">
                  <router-link :to="getLabRoute(item)" class="record-diary-link">
                    {{ item.lab.name || item.lab.uid }}
                  </router-link>
                  <span class="text-gray-300">/</span>
                  <router-link :to="getProjectRoute(item)" class="record-diary-link">
                    {{ item.project.name || item.project.uid }}
                  </router-link>
                  <span class="text-gray-300">/</span>
                  <router-link :to="getProtocolRoute(item)" class="record-diary-link">
                    {{ item.protocol.name || item.protocol.uid }}
                  </router-link>
                </div>
                <div class="flex flex-wrap items-center gap-2">
                  <h3 class="m-0 text-base font-semibold">
                    {{ getRecordTitle(item) }}
                  </h3>
                  <n-tag v-if="item.record_version > 1" size="small" type="success">
                    {{ $t("page.recordDiary.version", { version: item.record_version }) }}
                  </n-tag>
                </div>
              </div>

              <div class="flex shrink-0 items-center gap-2 text-sm text-gray-500">
                <n-avatar
                  round
                  :size="24"
                  :src="item.user.avatar_url || undefined"
                  fallback-src="/images/avatar_default.svg"
                  color="transparent"
                />
                <router-link
                  :to="{ name: 'user-profile', params: { username: item.user.username } }"
                  class="record-diary-link"
                >
                  {{ item.user.name || item.user.username }}
                </router-link>
                <n-time :time="new Date(getSubmittedAt(item))" type="relative" />
              </div>
            </header>

            <div v-if="isRecordExpanded(item)" class="record-diary-card__sticky-actions">
              <n-button
                type="primary"
                secondary
                size="small"
                @click="collapseRecord(item, $event)"
              >
                {{ $t("common.showLess") }}
              </n-button>
            </div>

            <div
              class="record-diary-report-preview"
              :class="{
                'record-diary-report-preview--collapsed': !isRecordExpanded(item),
                'record-diary-report-preview--expanded': isRecordExpanded(item),
              }"
            >
              <timeline-list-item
                :item="getTimelineItem(item)"
                :protocol-id="String(item.protocol.id)"
                :show-header="false"
              />
              <div
                v-if="!isRecordExpanded(item)"
                class="record-diary-report-preview__fade"
              >
                <n-button
                  type="primary"
                  quaternary
                  icon-placement="right"
                  @click="setRecordExpanded(item, true)"
                >
                  {{ $t("common.readMore") }}
                  <template #icon>
                    <icon-local-dropdown-outline />
                  </template>
                </n-button>
              </div>
            </div>

            <div v-if="isRecordExpanded(item)" class="mt-2 flex justify-center">
              <n-button
                type="primary"
                quaternary
                @click="collapseRecord(item, $event)"
              >
                {{ $t("common.showLess") }}
              </n-button>
            </div>

            <footer class="mt-4 flex justify-end">
              <n-button type="primary" quaternary size="small" @click="handleViewReport(item)">
                <template #icon>
                  <n-icon size="16">
                    <icon-tabler-external-link />
                  </n-icon>
                </template>
                {{ $t("page.recordDiary.viewReport") }}
              </n-button>
            </footer>
          </article>
        </n-timeline-item>
      </n-timeline>
    </template>

    <template #empty>
      <custom-empty :description="$t('page.recordDiary.empty')" class="py-20" />
    </template>
  </loading-list-wrapper>

  <teleport to="body">
    <transition name="record-diary-floating-collapse">
      <n-button
        v-if="hasExpandedRecord"
        class="record-diary-floating-collapse"
        type="primary"
        size="large"
        @click="collapseActiveRecord"
      >
        {{ $t("common.showLess") }}
      </n-button>
    </transition>
  </teleport>
</template>

<script setup lang="ts">
import type { FetchData, FetchPayload } from "@/components/common/loading-list-wrapper.vue"
import type { RecordDiaryEventItem, RecordDiaryItem, RecordDiarySubmitter } from "@/service/api/users"
import type { ITimelineItem } from "@/views/project-protocols/types"
import type { SelectOption } from "naive-ui"
import type { RouteLocationRaw } from "vue-router"
import LoadingListWrapper from "@/components/common/loading-list-wrapper.vue"
import TimelineListItem from "@/components/common/protocol-timeline/timeline-list-item.vue"
import { useRouterPush } from "@/composables/useRouterPush"
import { fetchProjectList } from "@/service/api/projects"
import { fetchAccessibleRecordDiary, fetchUserLabs, fetchUserProjects, fetchUserRecordDiary } from "@/service/api/users"
import { useAuthStore } from "@/store/modules/auth"
import { useProfileStore } from "@/views/profile/hooks/useProfileStore"
import { createProtocolRecordData } from "@/views/project-protocols/utils"
import { $t } from "@airalogy/shared/locales"
import { formatDate } from "@airalogy/shared/utils"
import RecordDiaryCalendar from "./modules/record-diary-calendar.vue"
import RecordDiaryHeatmap from "./modules/record-diary-heatmap.vue"

defineOptions({ name: "RecordDiary" })

type RecordDiaryReportTarget = RecordDiaryItem | RecordDiaryEventItem
type RecordDiaryViewMode = "heatmap" | "calendar"

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const profileStore = useProfileStore()
const { routerPushByKey } = useRouterPush()

const routeName = computed(() => String(route.name || ""))
const isProfileScope = computed(() => routeName.value === "profile-records")
const isProjectScope = computed(() => routeName.value === "project-records")
const isLabScope = computed(() => routeName.value === "lab-records")
const showLabFilter = computed(() => isProfileScope.value)
const showProjectFilter = computed(() => isProfileScope.value || isLabScope.value)
const showSubmitterFilter = computed(() => !isProfileScope.value)
const viewMode = ref<RecordDiaryViewMode>("heatmap")
const submitterFilter = ref<RecordDiarySubmitter>("all")
const selectedDate = ref<string>()
const selectedLabUid = ref("")
const selectedProjectUid = ref("")
const labLoading = ref(false)
const projectLoading = ref(false)
const labOptions = ref<SelectOption[]>([])
const projectOptions = ref<SelectOption[]>([])
const expandedRecordMap = ref<Record<string, boolean>>({})
const activeExpandedRecordKey = ref<string>()
const timelineItemCache = new Map<string, ITimelineItem>()
const submitterOptions = computed(() => [
  { label: $t("page.recordDiary.filterAllAccessible"), value: "all" },
  { label: $t("page.recordDiary.filterMySubmissions"), value: "me" },
])
const labFilterOptions = computed<SelectOption[]>(() => [
  { label: $t("page.recordDiary.filterAllLabs"), value: "" },
  ...labOptions.value,
])
const projectFilterOptions = computed<SelectOption[]>(() => [
  { label: $t("page.recordDiary.filterAllProjects"), value: "" },
  ...projectOptions.value,
])
const hasExpandedRecord = computed(() =>
  Boolean(activeExpandedRecordKey.value && expandedRecordMap.value[activeExpandedRecordKey.value]),
)
let labOptionsRequestSerial = 0
let projectOptionsRequestSerial = 0

const routeLabUid = computed(() => {
  const value = route.params.labUid
  return typeof value === "string" ? value : undefined
})

const projectUid = computed(() => {
  if (!isProjectScope.value) {
    return undefined
  }
  const value = route.params.projectUid
  return typeof value === "string" ? value : undefined
})

const routeLabQuery = computed(() => {
  const value = route.query.lab
  return typeof value === "string" ? value : ""
})

const routeProjectQuery = computed(() => {
  const value = route.query.project
  return typeof value === "string" ? value : ""
})

const effectiveLabUid = computed(() => {
  if (routeLabUid.value) {
    return routeLabUid.value
  }
  if (showLabFilter.value && selectedLabUid.value) {
    return selectedLabUid.value
  }
  return undefined
})

const effectiveProjectUid = computed(() => {
  if (projectUid.value) {
    return projectUid.value
  }
  if (showProjectFilter.value && selectedProjectUid.value) {
    return selectedProjectUid.value
  }
  return undefined
})

const targetUserId = computed(() => {
  if (isProfileScope.value) {
    return profileStore?.userInfo.value?.id || ""
  }
  return authStore.userInfo.id || ""
})

const canFetch = computed(() => {
  if (isProfileScope.value) {
    return Boolean(targetUserId.value)
  }

  return Boolean(authStore.userInfo.id)
})

const requestKey = computed(() => [
  routeName.value,
  targetUserId.value,
  effectiveLabUid.value || "all-labs",
  effectiveProjectUid.value || "all-projects",
  showSubmitterFilter.value ? submitterFilter.value : "profile",
  selectedDate.value || "all-dates",
].join(":"))

async function loadLabOptions() {
  if (!showLabFilter.value || !targetUserId.value) {
    labOptions.value = []
    return
  }

  const serial = ++labOptionsRequestSerial
  labLoading.value = true
  try {
    const data = await fetchUserLabs(
      targetUserId.value,
      { page: 1, pageSize: 1000, sortedBy: "updated_at" },
      `record-diary-labs:${targetUserId.value}:${serial}`,
    )

    if (serial !== labOptionsRequestSerial) {
      return
    }

    labOptions.value = (data?.labs || []).map(lab => ({
      label: lab.name || lab.uid,
      value: lab.uid,
    }))
  }
  finally {
    if (serial === labOptionsRequestSerial) {
      labLoading.value = false
    }
  }
}

async function loadProjectOptions() {
  if (!showProjectFilter.value) {
    projectOptions.value = []
    return
  }
  if (isProfileScope.value && !targetUserId.value) {
    projectOptions.value = []
    return
  }
  if (!isProfileScope.value && !effectiveLabUid.value) {
    projectOptions.value = []
    return
  }

  const serial = ++projectOptionsRequestSerial
  projectLoading.value = true
  try {
    const data = isProfileScope.value
      ? await fetchUserProjects(targetUserId.value, {
        labUid: effectiveLabUid.value,
        page: 1,
        pageSize: 1000,
        sortedBy: "updated_at",
      }, `record-diary-profile-projects:${targetUserId.value}:${effectiveLabUid.value || "all"}:${serial}`)
      : await fetchProjectList(
        { labUid: effectiveLabUid.value, page: 1, pageSize: 1000 },
        `record-diary-projects:${effectiveLabUid.value || "all"}:${serial}`,
      )

    if (serial !== projectOptionsRequestSerial) {
      return
    }

    projectOptions.value = (data?.projects || []).map(project => ({
      label: project.name || project.uid,
      value: project.uid,
    }))
  }
  finally {
    if (serial === projectOptionsRequestSerial) {
      projectLoading.value = false
    }
  }
}

async function fetcher(payload: FetchPayload): Promise<FetchData> {
  if (!canFetch.value) {
    return null
  }

  const queryPayload = {
    page: payload.currentPage,
    pageSize: payload.currentPageSize,
    labUid: effectiveLabUid.value,
    projectUid: effectiveProjectUid.value,
    submitter: showSubmitterFilter.value ? submitterFilter.value : undefined,
    dateFrom: selectedDate.value,
    dateTo: selectedDate.value,
  }
  const data = isProfileScope.value
    ? await fetchUserRecordDiary(targetUserId.value, queryPayload, payload.requestId)
    : await fetchAccessibleRecordDiary(queryPayload, payload.requestId)

  if (!data) {
    return null
  }

  return {
    list: data.records,
    total: data.total_count,
  }
}

function clearSelectedDate() {
  selectedDate.value = undefined
}

function setSelectedDate(value: string) {
  selectedDate.value = value
}

function getRecordKey(item: RecordDiaryItem) {
  return String(item.airalogy_record_id)
}

function getTimelineItemCacheKey(item: RecordDiaryItem) {
  return `${item.airalogy_record_id}:${item.record_version}`
}

function isRecordExpanded(item: RecordDiaryItem) {
  return expandedRecordMap.value[getRecordKey(item)] === true
}

function setRecordExpanded(item: RecordDiaryItem, expanded: boolean) {
  const key = getRecordKey(item)
  if (expanded) {
    expandedRecordMap.value = { [key]: true }
    activeExpandedRecordKey.value = key
    return
  }

  expandedRecordMap.value = { ...expandedRecordMap.value, [key]: false }
  if (activeExpandedRecordKey.value === key) {
    activeExpandedRecordKey.value = undefined
  }
}

function collapseRecord(item: RecordDiaryItem, event?: MouseEvent) {
  const target = event?.currentTarget as HTMLElement | null | undefined
  const card = target?.closest(".record-diary-card")
  setRecordExpanded(item, false)
  void nextTick(() => {
    card?.scrollIntoView({ block: "start", behavior: "smooth" })
  })
}

function collapseActiveRecord() {
  const key = activeExpandedRecordKey.value
  if (!key) {
    return
  }

  const card = document.querySelector<HTMLElement>(`.record-diary-card[data-record-key="${key}"]`)
  expandedRecordMap.value = { ...expandedRecordMap.value, [key]: false }
  activeExpandedRecordKey.value = undefined
  void nextTick(() => {
    card?.scrollIntoView({ block: "start", behavior: "smooth" })
  })
}

function getTimelineItem(item: RecordDiaryItem): ITimelineItem {
  const cacheKey = getTimelineItemCacheKey(item)
  const cachedItem = timelineItemCache.get(cacheKey)
  if (cachedItem) {
    return cachedItem
  }

  const timelineItem: ITimelineItem = {
    id: item.airalogy_record_id,
    recordId: item.record_id,
    operator: item.user.name || item.user.username,
    operatorId: String(item.user.id),
    operatorUsername: item.user.username,
    order: getRecordTitle(item),
    field: createProtocolRecordData(item.data),
    protocolId: String(item.protocol.id),
    protocolVersion: item.metadata.protocol_version,
    recordVersion: item.record_version,
    record: item,
    time: formatDate(getSubmittedAt(item), "date-time"),
  }

  timelineItemCache.set(cacheKey, timelineItem)
  return timelineItem
}

function getSubmittedAt(item: RecordDiaryItem) {
  return item.metadata.record_current_version_submission_time
}

function shouldShowDate(list: RecordDiaryItem[], index: number) {
  if (index === 0) {
    return true
  }

  return formatDate(getSubmittedAt(list[index]!), "date") !== formatDate(getSubmittedAt(list[index - 1]!), "date")
}

function getRecordTitle(item: RecordDiaryItem) {
  const recordNumber = item.metadata.record_num
  if (typeof recordNumber === "number") {
    return $t("page.recordDiary.recordTitle", { number: recordNumber })
  }

  return $t("page.recordDiary.recordFallback")
}

function getLabRoute(item: RecordDiaryItem): RouteLocationRaw {
  return { name: "lab-projects", params: { labUid: item.lab.uid } }
}

function getProjectRoute(item: RecordDiaryItem): RouteLocationRaw {
  return { name: "project-protocols", params: { labUid: item.lab.uid, projectUid: item.project.uid } }
}

function getProtocolRoute(item: RecordDiaryItem): RouteLocationRaw {
  return {
    name: "protocol-info",
    params: {
      labUid: item.lab.uid,
      projectUid: item.project.uid,
      protocolUid: item.protocol.uid,
    },
  }
}

function handleViewReport(item: RecordDiaryReportTarget) {
  routerPushByKey("protocol-record-report", {
    params: {
      labUid: item.lab.uid,
      projectUid: item.project.uid,
      protocolUid: item.protocol.uid,
      protocolVersion: item.metadata.protocol_version,
      recordId: item.record_id,
      recordVersion: String(item.record_version),
    },
  })
}

watch(requestKey, () => {
  expandedRecordMap.value = {}
  activeExpandedRecordKey.value = undefined
  timelineItemCache.clear()
})

watch(routeLabQuery, (value) => {
  if (value !== selectedLabUid.value) {
    selectedLabUid.value = value
  }
}, { immediate: true })

watch(routeProjectQuery, (value) => {
  if (value !== selectedProjectUid.value) {
    selectedProjectUid.value = value
  }
}, { immediate: true })

watch(selectedLabUid, (value) => {
  if (!showLabFilter.value || value === routeLabQuery.value) {
    return
  }

  selectedProjectUid.value = ""
  const nextQuery = { ...route.query }
  if (value) {
    nextQuery.lab = value
  }
  else {
    delete nextQuery.lab
  }
  delete nextQuery.project
  void router.replace({ path: route.path, query: nextQuery })
})

watch(selectedProjectUid, (value) => {
  if (!showProjectFilter.value || value === routeProjectQuery.value) {
    return
  }

  const nextQuery = { ...route.query }
  if (value) {
    nextQuery.project = value
  }
  else {
    delete nextQuery.project
  }
  void router.replace({ path: route.path, query: nextQuery })
})

watch(showProjectFilter, (visible) => {
  if (!visible) {
    selectedProjectUid.value = ""
  }
})

watch(showLabFilter, (visible) => {
  if (!visible) {
    selectedLabUid.value = ""
  }
})

watch([showLabFilter, targetUserId], () => {
  void loadLabOptions()
}, { immediate: true })

watch([showProjectFilter, isProfileScope, targetUserId, effectiveLabUid], () => {
  void loadProjectOptions()
}, { immediate: true })
</script>

<style scoped lang="sass">
.record-diary-page
  min-width: 0
  max-width: 100%
  padding: 4px 4px 24px

.record-diary-timeline
  min-width: 0
  padding-left: 8px

.record-diary-time-toolbar
  display: flex
  min-width: 0
  justify-content: flex-end

.record-diary-lab-filter,
.record-diary-project-filter
  width: 220px
  max-width: calc(100vw - 48px)

.record-diary-card
  min-width: 0
  border: 1px solid #E5E7EB
  border-radius: 8px
  background: #FFFFFF
  padding: 16px
  transition: border-color 0.2s ease, box-shadow 0.2s ease

  &:hover
    border-color: #BED7FF
    box-shadow: 0 8px 24px rgba(15, 23, 42, 0.06)

  &__sticky-actions
    position: sticky
    top: 76px
    z-index: 5
    display: flex
    justify-content: flex-end
    margin: 8px 0
    pointer-events: none

    :deep(.n-button)
      pointer-events: auto
      box-shadow: 0 8px 20px rgba(15, 23, 42, 0.12)

.record-diary-link
  color: #334155
  text-decoration: none

  &:hover
    color: #1A79FF

.record-diary-report-preview
  position: relative
  min-width: 0
  margin-top: 16px
  border: 1px solid #E5E7EB
  border-radius: 8px
  background: #FFFFFF

  &--collapsed
    overflow: hidden
    max-height: 260px

  &--expanded
    overflow: visible

  &__fade
    position: absolute
    right: 0
    bottom: 0
    left: 0
    display: flex
    justify-content: center
    background: linear-gradient(to top, #FFFFFF 0%, rgba(255, 255, 255, 0.94) 44%, rgba(255, 255, 255, 0) 100%)
    padding: 56px 0 12px

  :deep(.n-spin-container)
    min-height: 180px

  :deep(.n-spin-content)
    padding: 16px

  :deep(.n-form-item)
    margin-bottom: 10px

.record-diary-timeline
  :deep(.n-timeline-item-content)
    min-width: 0

.record-diary-floating-collapse
  position: fixed
  right: max(24px, env(safe-area-inset-right))
  bottom: max(24px, env(safe-area-inset-bottom))
  z-index: 2100
  box-shadow: 0 12px 28px rgba(15, 23, 42, 0.18)

.record-diary-floating-collapse-enter-active,
.record-diary-floating-collapse-leave-active
  transition: opacity 0.16s ease, transform 0.16s ease

.record-diary-floating-collapse-enter-from,
.record-diary-floating-collapse-leave-to
  opacity: 0
  transform: translateY(8px)

@media (max-width: 640px)
  .record-diary-floating-collapse
    right: 16px
    bottom: 16px
</style>
