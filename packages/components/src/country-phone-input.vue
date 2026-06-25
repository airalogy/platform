<template>
  <n-input-group>
    <!-- Country Selector -->
    <n-tooltip>
      <template #trigger>
        <n-select
          v-model:value="selectedCountryCode"
          :options="countryOptions"
          :loading="loading"
          :disabled="props.disabled"
          :placeholder="$t('common.selectCountry')"
          :render-tag="renderCountryTag"
          :filter="customCountryFilter"
          filterable
          clearable
          class="w-34"
          size="medium"
          :consistent-menu-width="false"
          :theme-overrides="{ peers: { InternalSelection: { textColorDisabled: '#333333' } } }"
          @update:value="handleCountryChange"
        />
      </template>
      Type country name, ISO code, or dial code to search
    </n-tooltip>
    <!-- Phone Number Input -->
    <n-input
      v-model:value="phoneNumber"
      :placeholder="phonePlaceholder"
      :disabled="props.disabled || !selectedCountryCode"
      :loading="loading"
      :type="props.mask ? 'password' : 'text'"
      :input-props="{ autocomplete: 'off' }"
      size="medium"
      class="phone-input flex-1"
      :class="{ error: !!error }"
      :maxlength="maxLength"
      @update:value="handlePhoneChange"
      @blur="handleBlur"
      @focus="handleFocus"
      @paste="handlePaste"
    />
  </n-input-group>
</template>

<script setup lang="tsx">
import { countryData, type CountryData } from "@airalogy/shared/constants/country-code"
import { $t } from "@airalogy/shared/locales"
import { useDebounceFn } from "@vueuse/core"
import MiniSearch from "minisearch"
import { NEllipsis, NIcon, type SelectOption, type SelectRenderTag } from "naive-ui"

interface Props {
  modelValue?: string
  placeholder?: string
  disabled?: boolean
  loading?: boolean
  error?: string
  defaultCountry?: string
  size?: "small" | "medium" | "large"
  mask?: boolean
}
const props = withDefaults(defineProps<Props>(), {
  modelValue: "",
  placeholder: "",
  disabled: false,
  loading: false,
  error: "",
  defaultCountry: "CN",
  size: "large",
  mask: false,
})

const emit = defineEmits<Emits>()

interface Emits {
  (e: "update:modelValue", value: string): void
  (e: "update:fullPhone", value: string): void
  (e: "update:country", country?: CountryData | null): void
  (e: "focus", event: FocusEvent): void
  (e: "blur", event: FocusEvent): void
}

// Reactive state
const selectedCountryCode = ref<string | null>(props.defaultCountry)
const phoneNumber = ref<string>("")
const isPasting = ref<boolean>(false)

// Computed properties
const selectedCountry = computed(() => {
  return countryData.find(country => country.isoCode === selectedCountryCode.value) || null
})

const fullPhoneNumber = computed(() => {
  if (!selectedCountry.value || !phoneNumber.value)
    return ""
  return `${selectedCountry.value.dialCode}${phoneNumber.value}`
})

const phonePlaceholder = computed(() => {
  if (props.placeholder)
    return props.placeholder
  if (selectedCountry.value) {
    return `Enter phone number for ${selectedCountry.value.name}`
  }
  return $t("common.selectCountry")
})

// Initialize MiniSearch for better country filtering
const countrySearch = new MiniSearch({
  fields: ["name", "isoCode", "dialCode"], // fields to index for full-text search
  storeFields: ["name", "isoCode", "dialCode"], // fields to return with search results
  searchOptions: {
    boost: { name: 2, isoCode: 1.5, dialCode: 1 }, // boost name matches
    fuzzy: 0.2, // enable fuzzy matching
    prefix: true, // enable prefix matching
  },
})

// Add country data to search index
countrySearch.addAll(countryData.map((country) => {
  const { icon: _icon, isoCode, ...rest } = country
  return {
    id: isoCode,
    isoCode,
    ...rest,
  }
}))

// Enhanced filter function using MiniSearch
function customCountryFilter(pattern: string, option: SelectOption): boolean {
  if (!pattern)
    return true

  const country = (option as any).country as CountryData
  if (!country)
    return false

  const searchTerm = Number.isNaN(Number(pattern)) ? pattern.toLowerCase().trim() : `+${pattern}`

  // Use MiniSearch for sophisticated matching
  const results = countrySearch.search(searchTerm, { boost: { isoCode: 2, dialCode: 2 } })

  // Check if this country is in the search results
  return results.some(result => result.id === country.isoCode)
}

// function customCountrySort(a: SelectOption, b: SelectOption): number {
//   const aCountry = (a as any).country as CountryData
//   const bCountry = (b as any).country as CountryData

//   return Number(aCountry.dialCode.slice(1)) - Number(bCountry.dialCode.slice(1))
// }

// Country options for select
const countryOptions = computed((): SelectOption[] => {
  return countryData.map(country => ({
    // label: `${country.name} (${country.dialCode})`,
    value: country.isoCode,
    country,
    label: () => (
      <div class="w-fit flex cursor-pointer items-center gap-2 py-1">
        <NIcon component={country.icon} />
        <div class="min-w-0 flex flex-1 flex-col">
          <NEllipsis class="text-sm font-medium">{country.name}</NEllipsis>
          <div class="text-xs text-gray-500">
            {`${country.isoCode} (${country.dialCode})`}
          </div>
        </div>
      </div>
    ),
  }))
})

// Custom renderers for country display
const renderCountryTag: SelectRenderTag = ({ option }) => {
  const { country } = option as { country: CountryData }
  if (!country) {
    return <>{option}</>
  }

  return (
    <div class="w-fit flex items-center gap-2">
      <NIcon component={country.icon} />
      <span class="text-gray-500">{country.isoCode}</span>
      <span class="font-medium">{country.dialCode}</span>
    </div>
  )
}

// Event handlers
function handleCountryChange(value: string | null) {
  selectedCountryCode.value = value || null
  const country = value ? countryData.find(c => c.isoCode === value) : null
  emit("update:country", country)
  updateModelValue()
}

// Enhanced phone change handler with logging
function handlePhoneChange(value: string) {
  // Check if the pasted value contains a dial code (international format)
  if (value.startsWith("+")) {
    // Try to find matching country by dial code
    const targetCountry = countryData.find(country => value.startsWith(country.dialCode))

    if (targetCountry) {
      // Set the country and extract the phone number without dial code
      selectedCountryCode.value = targetCountry.isoCode
      phoneNumber.value = value.trim().slice(targetCountry.dialCode.length).trim()

      // Emit country change
      emit("update:country", targetCountry)
      updateModelValue()

      // Reset paste flag after processing
      isPasting.value = false
      return
    }
    else {
      // console.log("❌ No matching country found for:", value)
    }
  }

  // Default behavior for regular phone number input
  phoneNumber.value = value.trim()
  updateModelValue()

  // Reset paste flag after processing
  isPasting.value = false
}

function handleFocus(event: FocusEvent) {
  emit("focus", event)
}

function handleBlur(event: FocusEvent) {
  emit("blur", event)
}

function updateModelValue() {
  emit("update:fullPhone", fullPhoneNumber.value)
  emit("update:modelValue", phoneNumber.value)
}

// Initialize with default country and parse existing value
onMounted(() => {
  // Set default country
  if (props.defaultCountry && !selectedCountryCode.value) {
    selectedCountryCode.value = props.defaultCountry
  }
})

// Parse phone number with country code (now debounced)
const parsePhoneNumber = useDebounceFn((value: string) => {
  if (!value)
    return

  const targetCountry = countryData.find(country => value.startsWith(country.dialCode))

  if (targetCountry) {
    selectedCountryCode.value = targetCountry.isoCode
    phoneNumber.value = value.substring(targetCountry.dialCode.length).trim()
  }
}, 300) // 300ms debounce delay

// Watch for external modelValue changes
watch(() => props.modelValue, (newValue) => {
  if (newValue !== fullPhoneNumber.value) {
    parsePhoneNumber(newValue || "")
  }
}, { immediate: true })

const maxLength = computed(() => {
  // Allow longer input during paste operations to enable country detection
  if (isPasting.value) {
    return 20 // Temporary higher limit for paste operations
  }

  if (selectedCountry.value?.isoCode === "CN") {
    return 11
  }

  return 20
})

// Add paste event handler
function handlePaste(event: ClipboardEvent) {
  isPasting.value = true
}
</script>

<style scoped lang="sass">
</style>
