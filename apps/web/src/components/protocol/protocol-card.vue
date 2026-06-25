<template>
  <n-card
    header-class="!pb-0 !pt-3 !pl-5 !pr-3"
    content-class="!px-5 !py-0"
    footer-class="!px-5 !py-3"
    size="small"
    :theme-overrides="{ borderRadius: '14px', borderColor: '#CCD0D7BB' }"
  >
    <template #header>
      <div class="flex items-center justify-between">
        <router-link
          :to="{ name: 'protocol-detail', params: { labUid: props.protocol.lab.uid, projectUid: props.protocol.project.uid, protocolUid: props.protocol.uid } }"
          class="break-all text-base font-bold transition-colors duration-300 hover:text-[#1A79FF]"
        >
          {{ protocol.name }}
        </router-link>
        <n-tag size="tiny" class="ml-2 h-5 whitespace-nowrap" type="success" round>
          v{{ protocol.latest_version }}
        </n-tag>
        <tooltip-button
          v-if="protocol.airalogy_id"
          round
          quaternary
          size="tiny"
          type="default"
          class="ml-2 mr-auto h-8 w-8"
          @click.stop="handleStartRecording"
        >
          {{ $t("common.id") }}
          <template #tooltip>
            <copy-to-clip :text="protocol.airalogy_id" show-success color="#ffffff" />
          </template>
        </tooltip-button>
        <add-to-bookmarker-modal
          type="protocol"
          :starred="isStarred"
          :trigger="props.isStarred ? $t('common.unstar') : $t('common.star')"
          :tooltip="$t('page.hub.protocolCard.addToBookmarks')"
          :button-props="{ size: 'small', quaternary: true, themeOverrides: { colorHover: '#0084E2' } }"
          :icon-props="{ size: 18, color: isStarred ? '#E3B341' : '#A1A4AF' }"
          :protocol-id="protocol.id"
          @modal:add-to-bookmarker="folders => isStarred = folders.length > 0"
        />

        <apply-protocol-modal
          show-trigger
          :protocol-id="protocol.id"
          :button-props="{ size: 'small', quaternary: true, themeOverrides: { colorHover: '#0084E2' } }"
          :icon-props="{ size: 16, color: '#A1A4AF' }"
          :trigger="$t('common.reuse')"
          @modal:apply-protocol="handleApplyClick"
        />
        <!--
        <tooltip-button
          size="small"
          tooltip="Apply this protocol to your project"
          @click.stop="handleApplyClick"
        >
          <template #icon>
            <n-icon :size="16" color="#A1A4AF">
              <icon-solar-refresh-square-bold />
            </n-icon>
          </template>
          <span>Reuse</span>
        </tooltip-button> -->
        <!--
        <tooltip-button
          quaternary
          size="small"
          tooltip="Download this protocol"
          class="mr-auto"
          @click.stop="handleDownloadClick"
        >
          <template #icon>
            <n-icon :size="14" color="#A1A4AF">
              <icon-local-record-filled />
            </n-icon>
          </template>
          <span>{{ formatNumber(protocol.download_count) }}</span>
        </tooltip-button> -->
      </div>
    </template>

    <div v-if="protocol.description" class="relative mt-1">
      <div
        ref="descriptionRef"
        class="pr-6 text-sm text-gray-600 leading-5" :class="[{ 'line-clamp-2': !isExpanded }]"
      >
        {{ protocol.description }}
      </div>
      <n-button
        v-if="showToggle"
        text
        size="tiny"
        class="expand-toggle absolute right-0 top-5 px-0"
        :title="isExpanded ? $t('common.showLess') : $t('common.readMore')"
        @click="isExpanded = !isExpanded"
      >
        <n-icon :size="14" color="#A1A4AF">
          <icon-tabler-chevron-up v-if="isExpanded" />
          <icon-tabler-chevron-down v-else />
        </n-icon>
      </n-button>
    </div>
    <div v-if="protocol.disciplines?.length" class="my-1 flex flex-wrap gap-1">
      <n-tag v-for="(discipline, idx) in protocol.disciplines" :key="idx" :bordered="false" size="small" :color="{ color: '#E8F3FF', textColor: '#1A79FF' }">
        {{ discipline }}
      </n-tag>
    </div>
    <div v-if="protocol.keywords?.length" class="my-1 flex flex-wrap gap-1">
      <n-tag
        v-for="(tag, idx) in protocol.keywords"
        :key="idx"
        size="small"
        round
        :color="{ textColor: '#666', borderColor: '#CACACA', color: 'transparent' }"
      >
        {{ tag }}
      </n-tag>
    </div>
    <div
      class="my-2 flex flex-1 items-center justify-start overflow-hidden text-sm"
    >
      <span class="mr-2">{{ $t("common.from") }}</span>
      <protocol-path-tooltip :protocol-info="props.protocol" :show-protocol-name="false" />
    </div>
    <template #footer>
      <div class="flex items-center gap-3 text-xs">
        <n-tooltip trigger="hover">
          <template #trigger>
            <div class="min-w-10 flex cursor-pointer items-center gap-2 text-xs">
              <n-icon :size="14" :color="isStarred ? '#FFC107' : '#A1A4AF'">
                <icon-tabler-star-filled />
              </n-icon>
              <span>{{ formatNumber(protocol.stars_count || 0) }}</span>
            </div>
          </template>
          {{ $t("common.starsCount") }}
        </n-tooltip>

        <n-tooltip trigger="hover">
          <template #trigger>
            <div class="min-w-10 flex cursor-pointer items-center gap-2 text-xs" @click.stop="handleApplyClick">
              <n-icon :size="13" color="#A1A4AF">
                <icon-local-reuse />
              </n-icon>
              <span>{{ formatNumber(protocol.forks_count || 0) }}</span>
            </div>
          </template>
          {{ $t("common.reusesCount") }}
        </n-tooltip>

        <n-tooltip trigger="hover">
          <template #trigger>
            <div class="min-w-10 flex cursor-pointer items-center gap-2 text-xs" @click.stop="handleDownloadClick">
              <n-icon :size="14" color="#A1A4AF">
                <icon-local-record-filled />
              </n-icon>
              <span>{{ formatNumber(props.protocol.records_count || 0) }}</span>
            </div>
          </template>
          {{ $t("common.recordsCount") }}
        </n-tooltip>

        <!-- <div class="h-3 w-0.5 rounded-xl bg-gray-200" /> -->
        <n-tooltip trigger="hover">
          <template #trigger>
            <n-time
              class="ml-auto whitespace-nowrap text-xs text-gray-500"
              :time="dayjs(protocol.created_at).valueOf()"
              type="relative"
            />
          </template>
          {{ $t("common.updatedAt") }} {{ formatDate(protocol.created_at, "date-time") }}
        </n-tooltip>
        <div class="h-3 w-0.5 rounded-xl bg-gray-200" />
        <n-tooltip trigger="hover">
          <template #trigger>
            <div class="flex items-center gap-1">
              <n-icon :size="14">
                <icon-fluent-scales-24-regular />
              </n-icon>
              {{ protocol.metadata?.license || 'Apache-2.0' }}
            </div>
          </template>
          {{ $t("common.license") }}: {{ protocol.metadata?.license || 'Apache-2.0' }}
        </n-tooltip>
      </div>
    </template>
  </n-card>
</template>

<script setup lang="ts">
import ProtocolPathTooltip from "@/components/protocol/protocol-path-tooltip.vue"
import { useRouterPush } from "@/composables/useRouterPush"
import ApplyProtocolModal from "@/views/hub/components/apply-protocol-modal.vue"
import CopyToClip from "@airalogy/components/src/copy-to-clip.vue"
import TooltipButton from "@airalogy/components/tooltip-button.vue"
import { formatNumber } from "@airalogy/shared"
import { $t } from "@airalogy/shared/locales"
import { formatDate } from "@airalogy/shared/utils"
import dayjs from "dayjs"
import { nextTick, ref, watch } from "vue"
import { useLoading } from "../../composables"

interface IProps {
  protocol: Api.Hub.Protocol
  isStarred?: boolean
}

const props = withDefaults(defineProps<IProps>(), {
  isStarred: false,
})

const emit = defineEmits<IEmits>()

interface IEmits {
  (e: "update:isStarred", isStarred: boolean): void
  (e: "update:stars", stars: number): void
  (e: "apply", protocol: Api.Hub.Protocol): void
}

const isStarred = useVModel(props, "isStarred", emit)
const isExpanded = ref(false)
const showToggle = ref(false)
const descriptionRef = ref<HTMLElement | null>(null)

const { routerPushByKey } = useRouterPush()
const colors: { color: string, borderColor: string, textColor: string }[] = [
  { color: "#E3F2FD", borderColor: "#90CAF9", textColor: "#1976D2" },
  { color: "#F3E5F5", borderColor: "#CE93D8", textColor: "#7B1FA2" },
  { color: "#E8F5E9", borderColor: "#A5D6A7", textColor: "#388E3C" },
  { color: "#FFF3E0", borderColor: "#FFCC80", textColor: "#F57C00" },
  { color: "#E1F5FE", borderColor: "#81D4FA", textColor: "#0288D1" },
  { color: "#F3E5F5", borderColor: "#B39DDB", textColor: "#512DA8" },
  { color: "#FCE4EC", borderColor: "#F48FB1", textColor: "#C2185B" },
]

const { loadingState, startLoading, endLoading } = useLoading(false, ["star"])

function updateToggleVisibility() {
  if (isExpanded.value) {
    return
  }
  const el = descriptionRef.value
  if (!el) {
    return
  }
  showToggle.value = el.scrollHeight - el.clientHeight > 1
}

useResizeObserver(descriptionRef, () => {
  updateToggleVisibility()
})

watch(
  () => props.protocol.description,
  async () => {
    await nextTick()
    updateToggleVisibility()
  },
  { immediate: true },
)

watch(
  isExpanded,
  async (expanded) => {
    if (!expanded) {
      await nextTick()
      updateToggleVisibility()
    }
  },
)

function handleNavigate() {
  if (!props.protocol) {
    return
  }

  routerPushByKey("protocol-detail", {
    params: {
      labUid: props.protocol.lab.uid,
      projectUid: props.protocol.project.uid,
      protocolUid: props.protocol.uid,
    },
  })
}

function handleDownloadClick() {
  console.log("download clicked")
}

function handleApplyClick() {
  emit("apply", props.protocol)
}

function handleStartRecording() {

}
</script>

<style scoped lang="scss">
:deep(.n-rate .n-rate__item:not(:first-child)) {
  margin-left: 3px !important;
}

.expand-toggle {
  color: #A1A4AF;
  transition: color 0.2s ease;
}

.expand-toggle:hover {
  color: #1A79FF;
}
</style>
