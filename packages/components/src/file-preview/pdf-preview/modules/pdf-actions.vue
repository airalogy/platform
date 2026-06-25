<template>
  <!-- Floating Controls -->
  <div class="absolute bottom-4 left-4 flex items-center gap-1 rounded-lg bg-white p-2 shadow-lg backdrop-blur-sm">
    <!-- Collapse/Expand Button with Hover Controls -->
    <n-popover
      v-if="!isControlsExpanded"
      trigger="hover"
      placement="top"
      :show-arrow="false"
      :delay="200"
    >
      <template #trigger>
        <n-button
          quaternary
          size="small"
          class="!px-1"
          @click="isControlsExpanded = !isControlsExpanded"
        >
          <template #icon>
            <n-icon :size="18">
              <icon-ion-menu />
            </n-icon>
          </template>
        </n-button>
      </template>

      <!-- Vertical Controls in Hover -->
      <n-space vertical :size="4">
        <!-- Page Navigation -->
        <n-space align="center" :size="4">
          <n-popover trigger="hover" placement="top" :delay="300">
            <template #trigger>
              <n-button
                circle
                size="small"
                :disabled="!canGoToPrevious || loading"
                @click="$emit('previousPage')"
              >
                <template #icon>
                  <n-icon :size="16">
                    <icon-ion-chevron-back />
                  </n-icon>
                </template>
              </n-button>
            </template>
            <div class="text-center">
              <div class="font-medium">
                Previous Page
              </div>
              <div class="mt-1 text-xs text-gray-500">
                <span class="kbd">←</span> or click
              </div>
            </div>
          </n-popover>

          <span class="min-w-12 text-center text-xs text-gray-600">
            {{ currentPage }} / {{ totalPages }}
          </span>

          <n-popover trigger="hover" placement="top" :delay="300">
            <template #trigger>
              <n-button
                circle
                size="small"
                :disabled="!canGoToNext || loading"
                @click="$emit('nextPage')"
              >
                <template #icon>
                  <n-icon :size="16">
                    <icon-ion-chevron-forward />
                  </n-icon>
                </template>
              </n-button>
            </template>
            <div class="text-center">
              <div class="font-medium">
                Next Page
              </div>
              <div class="mt-1 text-xs text-gray-500">
                <span class="kbd">→</span> or click
              </div>
            </div>
          </n-popover>
        </n-space>

        <!-- Zoom Controls -->
        <n-space align="center" :size="4" justify="center">
          <n-popover trigger="hover" placement="top" :delay="300">
            <template #trigger>
              <n-button
                circle
                size="small"
                :disabled="loading"
                @click="$emit('zoomOut')"
              >
                <template #icon>
                  <n-icon :size="16">
                    <icon-ion-remove />
                  </n-icon>
                </template>
              </n-button>
            </template>
            <div class="text-center">
              <div class="font-medium">
                Zoom Out
              </div>
              <div class="mt-1 text-xs text-gray-500">
                <span class="kbd">-</span> or <span class="kbd">Ctrl</span> + <span class="kbd">Wheel ↓</span>
              </div>
            </div>
          </n-popover>

          <span class="min-w-12 text-center text-xs text-gray-600">
            {{ Math.round(scale * 100) }}%
          </span>

          <n-popover trigger="hover" placement="top" :delay="300">
            <template #trigger>
              <n-button
                circle
                size="small"
                :disabled="loading"
                @click="$emit('zoomIn')"
              >
                <template #icon>
                  <n-icon :size="16">
                    <icon-ion-add />
                  </n-icon>
                </template>
              </n-button>
            </template>
            <div class="text-center">
              <div class="font-medium">
                Zoom In
              </div>
              <div class="mt-1 text-xs text-gray-500">
                <span class="kbd">+</span> or <span class="kbd">Ctrl</span> + <span class="kbd">Wheel ↑</span>
              </div>
            </div>
          </n-popover>
        </n-space>
      </n-space>
    </n-popover>

    <!-- Regular Collapse Button when Expanded -->
    <tooltip-button
      v-else
      :icon="IconIonCollapse"
      :button-props="{
        circle: true,
        size: 'small',
        quaternary: true,
      }"
      tooltip="Collapse controls"
      :icon-props="{ size: 18 }"
      @click="isControlsExpanded = !isControlsExpanded"
    />

    <template v-if="isControlsExpanded">
      <n-divider vertical class="!mx-1" />

      <n-popover trigger="hover" placement="top" :delay="300">
        <template #trigger>
          <n-button
            circle
            size="small"
            :disabled="!canGoToPrevious || loading"
            @click="$emit('previousPage')"
          >
            <template #icon>
              <n-icon :size="16">
                <icon-ion-chevron-back />
              </n-icon>
            </template>
          </n-button>
        </template>
        <div class="text-center">
          <div class="font-medium">
            Previous Page
          </div>
          <div class="mt-1 text-xs text-gray-500">
            <span class="kbd">←</span> or click
          </div>
        </div>
      </n-popover>

      <!-- Page Info Button with Popover -->
      <n-popover trigger="click" placement="top">
        <template #trigger>
          <n-button :disabled="loading" quaternary size="small">
            {{ currentPage }} / {{ totalPages }}
          </n-button>
        </template>

        <n-space vertical :size="8">
          <div class="text-center">
            <div class="mb-1 text-xs text-gray-500">
              Go to page
            </div>
            <n-space align="center" :size="4" justify="center">
              <n-input
                v-model:value="localPageInput"
                size="tiny"
                style="width: 60px"
                :disabled="loading"
                @blur="handlePageInput"
                @keydown.enter="handlePageInput"
              />
              <span class="text-xs text-gray-500">/ {{ totalPages }}</span>
            </n-space>
          </div>

          <n-divider class="!my-1" />

          <div class="zoom-display text-center">
            <div class="mb-1 text-xs text-gray-500">
              Zoom
            </div>
            <div class="text-sm font-medium">
              {{ Math.round(scale * 100) }}%
            </div>
          </div>

          <n-divider class="!my-1" />

          <div class="text-center">
            <div class="mb-2 text-xs text-gray-700 font-medium">
              Interaction Tips
            </div>
            <div class="text-xs text-gray-500 space-y-1">
              <div>• Drag to pan when zoomed</div>
              <div>• <span class="kbd">Ctrl</span> + Wheel to zoom</div>
              <div>• <span class="kbd">Shift</span> + Wheel to scroll horizontally</div>
              <div>• Double-click to fit width</div>
            </div>
          </div>

          <n-space vertical :size="4">
            <n-popover trigger="hover" placement="right" :delay="300">
              <template #trigger>
                <n-button
                  size="tiny"
                  block
                  :disabled="loading"
                  @click="$emit('fitToWidth')"
                >
                  Fit Width
                </n-button>
              </template>
              <div class="text-center">
                <div class="font-medium">
                  Fit to Width
                </div>
                <div class="mt-1 text-xs text-gray-500">
                  Double-click to fit
                </div>
              </div>
            </n-popover>
            <n-popover trigger="hover" placement="right" :delay="300">
              <template #trigger>
                <n-button
                  size="tiny"
                  block
                  :disabled="loading"
                  @click="$emit('fitToHeight')"
                >
                  Fit Height
                </n-button>
              </template>
              <div class="text-center">
                <div class="font-medium">
                  Fit to Height
                </div>
                <div class="mt-1 text-xs text-gray-500">
                  Adjust to screen height
                </div>
              </div>
            </n-popover>
          </n-space>
        </n-space>
      </n-popover>

      <n-popover trigger="hover" placement="top" :delay="300">
        <template #trigger>
          <n-button
            circle
            size="small"
            :disabled="!canGoToNext || loading"
            @click="$emit('nextPage')"
          >
            <template #icon>
              <n-icon :size="16">
                <icon-ion-chevron-forward />
              </n-icon>
            </template>
          </n-button>
        </template>
        <div class="text-center">
          <div class="font-medium">
            Next Page
          </div>
          <div class="mt-1 text-xs text-gray-500">
            <span class="kbd">→</span> or click
          </div>
        </div>
      </n-popover>

      <n-divider vertical class="!mx-1" />

      <!-- Zoom Controls -->
      <n-popover trigger="hover" placement="top" :delay="300">
        <template #trigger>
          <n-button
            circle
            size="small"
            :disabled="loading"
            @click="$emit('zoomOut')"
          >
            <template #icon>
              <n-icon :size="16">
                <icon-ion-remove />
              </n-icon>
            </template>
          </n-button>
        </template>
        <div class="text-center">
          <div class="font-medium">
            Zoom Out
          </div>
          <div class="mt-1 text-xs text-gray-500">
            <span class="kbd">-</span> or <span class="kbd">Ctrl</span> + <span class="kbd">Wheel ↓</span>
          </div>
        </div>
      </n-popover>

      <n-popover trigger="hover" placement="top" :delay="300">
        <template #trigger>
          <n-button
            circle
            size="small"
            :disabled="loading"
            @click="$emit('zoomIn')"
          >
            <template #icon>
              <n-icon :size="16">
                <icon-ion-add />
              </n-icon>
            </template>
          </n-button>
        </template>
        <div class="text-center">
          <div class="font-medium">
            Zoom In
          </div>
          <div class="mt-1 text-xs text-gray-500">
            <span class="kbd">+</span> or <span class="kbd">Ctrl</span> + <span class="kbd">Wheel ↑</span>
          </div>
        </div>
      </n-popover>
    </template>
  </div>
</template>

<script setup lang="ts">
import IconIonAdd from "~icons/ion/add"
import IconIonChevronBack from "~icons/ion/chevron-back"
import IconIonChevronForward from "~icons/ion/chevron-forward"
import IconIonMenu from "~icons/ion/menu"
import IconIonRemove from "~icons/ion/remove"
import IconIonCollapse from "~icons/tabler/layout-sidebar-left-collapse"
import { NButton, NDivider, NIcon, NInput, NPopover, NSpace } from "naive-ui"
import { ref } from "vue"

interface Props {
  currentPage: number
  totalPages: number
  scale: number
  canGoToPrevious: boolean
  canGoToNext: boolean
  loading: boolean
  pageInputValue: string
}

interface Emits {
  (e: "previousPage"): void
  (e: "nextPage"): void
  (e: "zoomIn"): void
  (e: "zoomOut"): void
  (e: "fitToWidth"): void
  (e: "fitToHeight"): void
  (e: "pageInput", value: string): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

// Control popup menu visibility
const isControlsExpanded = ref(true)
const localPageInput = ref(props.pageInputValue)

function handlePageInput() {
  emit("pageInput", localPageInput.value)
}
</script>

<style scoped lang="sass">
.kbd
  display: inline-block
  padding: 2px 4px
  font-size: 10px
  font-family: monospace
  color: #374151
  background-color: #f3f4f6
  border: 1px solid #d1d5db
  border-radius: 3px
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.1)
  font-weight: 600
  text-transform: uppercase
  letter-spacing: 0.5px

.dark .kbd
  color: #d1d5db
  background-color: #374151
  border-color: #6b7280
</style>
