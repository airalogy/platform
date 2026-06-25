<template>
  <!-- Filter Actions Row -->
  <div class="flex items-center gap-3">
    <!-- Dynamic Filter Input -->
    <n-date-picker
      v-if="filterType === 'date'"
      v-model:value="dateRange"
      type="daterange"
      clearable
      size="small"
      :theme-overrides="datePickerOverrides"
      :actions="null"
      class="flex-1"
      @update:value="handleDateRangeChange"
    />

    <global-add-member
      v-if="filterType === 'member'"
      type="lab"
      class="flex-1"
      :theme-overrides="selectOverrides"
      size="small"
      @update:select="handleMemberSelect"
    />

    <n-select
      v-if="filterType === 'tag'"
      v-model:value="selectedTags"
      :options="tagOptions"
      multiple
      filterable
      tag
      size="small"
      :theme-overrides="selectOverrides"
      placeholder="Enter or select tags"
      class="flex-1"
      @update:value="handleTagsChange"
    />

    <!-- Clear Button -->
    <n-button
      v-if="hasActiveFilters"
      text
      type="error"
      size="tiny"
      :theme-overrides="buttonOverrides"
      @click="handleClearFilters"
    >
      <template #icon>
        <n-icon>
          <icon-ion-close-circle />
        </n-icon>
      </template>
      Clear All
    </n-button>
  </div>
</template>

<script setup lang="ts">
import type { ICustomSelectOption } from "@/components/common/global-add-member.vue"
import type { ButtonProps, DatePickerProps, SelectOption } from "naive-ui"
import { formatDate } from "@airalogy/shared/utils"
import IconIonCloseCircle from "~icons/ion/close-circle"

interface Props {
  type: "protocol" | "record" | "discussion"
}

const props = defineProps<Props>()

const emit = defineEmits<Emits>()

interface Emits {
  (e: "update:filters", filters: {
    dateRange?: [number, number] | null
    userIds?: string[]
    tags?: string[]
  }): void
}

// Theme Overrides
const selectOverrides = {
  peers: {
    InternalSelection: {
      heightSmall: "36px",
      paddingSmall: "0 8px",
      color: "transparent",
    },
  },
  common: {
    borderRadius: "16px",
  },
}

const datePickerOverrides: DatePickerProps["themeOverrides"] = {
  peers: {
    Input: {
      heightSmall: "36px",
      paddingSmall: "0 8px",
      color: "transparent",
    },
  },
  common: {
    borderRadius: "16px",
  },
}

const buttonOverrides = {
  paddingRoundSmall: "4px 12px",
  heightSmall: "24px",
  fontSizeSmall: "12px",
} satisfies ButtonProps["themeOverrides"]

const tagOverrides = {
  color: "rgba(0, 0, 0, 0.06)",
  textColor: "rgb(51, 54, 57)",
  closeIconColor: "rgb(51, 54, 57)",
  closeIconColorHover: "rgb(51, 54, 57)",
  closeIconColorPressed: "rgb(51, 54, 57)",
  borderRadius: "12px",
  heightSmall: "24px",
  fontSizeSmall: "12px",
  padding: "0 12px",
}

// Filter Type Selection
// const filterType = ref<"date" | "member" | "tag" | null>(null)
// const filterTypeOptions = computed(() => {
//   const options: SelectOption[] = []

//   if (props.type === "record") {
//     options.push(
//       { label: "Date", value: "date", icon: IconIonCalendar },
//       { label: "Member", value: "member", icon: IconIonPerson },
//     )
//   }

//   if (props.type === "discussion") {
//     options.push(
//       { label: "Date", value: "date", icon: IconIonCalendar },
//       { label: "Member", value: "member", icon: IconIonPerson },
//       { label: "Tags", value: "tag", icon: IconIonPricetag },
//     )
//   }

//   if (props.type === "protocol") {
//     options.push(
//       { label: "Date", value: "date", icon: IconIonCalendar },
//       { label: "Tags", value: "tag", icon: IconIonPricetag },
//     )
//   }

//   return options
// })

const filterType = computed(() => {
  const { type } = props
  switch (type) {
    case "record":
      return "date"
    case "discussion":
      return "member"
    case "protocol":
      return "tag"
  }

  return null
})
// Date Range Filter
const dateRange = ref<[number, number] | null>(null)
function handleDateRangeChange(value: [number, number] | null) {
  dateRange.value = value
  emitFilters()
}

function formatDateRange(range: [number, number]) {
  return `${formatDate(range[0], "month-day")} - ${formatDate(range[1], "date")}`
}

// Member Filter
const selectedMembers = ref<ICustomSelectOption[]>([])
function handleMemberSelect(members: ICustomSelectOption[]) {
  selectedMembers.value = members
  emitFilters()
}

function handleRemoveMember(member: ICustomSelectOption) {
  selectedMembers.value = selectedMembers.value.filter(m => m.value !== member.value)
  emitFilters()
}

// Tag Filter
const selectedTags = ref<string[]>([])
const tagOptions = ref<SelectOption[]>([
  { label: "Synthesis", value: "synthesis" },
  { label: "Analysis", value: "analysis" },
  { label: "Optimization", value: "optimization" },
  { label: "Characterization", value: "characterization" },
])

function handleTagsChange(tags: string[]) {
  selectedTags.value = tags
  emitFilters()
}

function handleRemoveTag(tag: string) {
  selectedTags.value = selectedTags.value.filter(t => t !== tag)
  emitFilters()
}

// Clear Filters
const hasActiveFilters = computed(() => {
  return Boolean(
    dateRange.value
    || selectedMembers.value.length
    || selectedTags.value.length,
  )
})

function handleClearFilters() {
  dateRange.value = null
  selectedMembers.value = []
  selectedTags.value = []
  emitFilters()
}

function handleClearDateRange() {
  dateRange.value = null
  emitFilters()
}

// Emit Filters
function emitFilters() {
  emit("update:filters", {
    dateRange: dateRange.value,
    userIds: selectedMembers.value.map(m => m.value),
    tags: selectedTags.value,
  })
}
</script>

<style scoped>
</style>
