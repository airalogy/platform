<template>
  <n-modal
    v-model:show="showModal"
    preset="card"
    :title="$t('page.login.testingNotice.title')"
    :bordered="false"
    size="large"
    class="max-w-90vw w-140"
    :mask-closable="false"
    :show-icon="false"
    header-class="testing-dialog__header"
    content-class="testing-dialog__content"
  >
    <template #icon>
      <n-icon size="24" color="#1890ff">
        <icon-tabler-info-circle />
      </n-icon>
    </template>

    <div class="testing-notification">
      <div class="notification-icon mb-4 text-center">
        <n-icon size="48" color="#52c41a">
          <icon-tabler-circle-check />
        </n-icon>
      </div>

      <div class="notification-content">
        <h3 class="mb-4 text-center text-lg text-gray-800 font-semibold">
          {{ $t("page.login.testingNotice.successTitle") }}
        </h3>

        <div class="testing-message mb-6 border-l-4 border-primary-400 rounded-lg bg-primary-50 p-4">
          <div class="flex items-start">
            <n-icon size="20" color="#1890ff" class="mr-3 mt-0.5 flex-shrink-0">
              <icon-tabler-info-circle />
            </n-icon>
            <div class="text-sm text-gray-700 leading-relaxed">
              {{ $t("page.login.testingNotice.message") }}
            </div>
          </div>
        </div>

        <div class="text-center text-sm text-gray-600">
          <p>{{ $t("page.login.testingNotice.helper") }}</p>
        </div>
      </div>
    </div>

    <template #action>
      <div class="flex justify-center gap-4">
        <n-button
          size="large"
          class="min-w-32"
          @click="handleLater"
        >
          {{ $t("page.login.testingNotice.exploreLater") }}
        </n-button>
        <n-button
          type="primary"
          size="large"
          class="min-w-32"
          @click="handleGetStarted"
        >
          {{ $t("page.login.testingNotice.getStarted") }}
        </n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { useRouterPush } from "@/composables/useRouterPush"
import { $t } from "@airalogy/shared/locales"

interface Props {
  show: boolean
}

interface Emits {
  (e: "update:show", value: boolean): void
  (e: "getStarted"): void
  (e: "dismiss"): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const { routerPushByKey } = useRouterPush()

const showModal = computed({
  get: () => props.show,
  set: value => emit("update:show", value),
})

function handleGetStarted() {
  emit("getStarted")
  emit("update:show", false)
  routerPushByKey("hub")
}

function handleLater() {
  emit("dismiss")
  emit("update:show", false)
  // Navigate to home/dashboard
  // routerPushByKey("root")
}
</script>

<style scoped lang="sass">
.testing-notification
  text-align: left

.notification-icon
  animation: bounce-in 0.6s ease-out

.testing-message
  background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%)

.notification-content
  line-height: 1.6

:deep(.testing-dialog__header)
  text-align: center
  border-bottom: 1px solid #f0f0f0
  padding: 1.5rem

:deep(.testing-dialog__content)
  padding: 2rem 1.5rem 1.5rem

@keyframes bounce-in
  0%
    transform: scale(0.3)
    opacity: 0
  50%
    transform: scale(1.05)
  70%
    transform: scale(0.9)
  100%
    transform: scale(1)
    opacity: 1
</style>
