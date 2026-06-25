<template>
  <n-card
    :bordered="false"
    :title="title"
    class="m-auto h-fit min-w-320px w-full md:top-0 md:w-500px"
    header-class="form__title max-md:!px-5"
    content-class="max-md:!px-5"
    size="huge"
  >
    <template v-if="props.type === 'login'">
      <pwd-login />
    </template>
    <template v-else>
      <pwd-sign-up />
    </template>

    <form-overlay
      v-if="showOverlay"
      :title="overlayTitle"
      :description="overlayDescription"
      :button-text="overlayButtonText"
      @button:click="handleOverlayButtonClick"
    />
  </n-card>
</template>

<script setup lang="ts">
import { useRouterPush } from "@/composables/useRouterPush"
import { $t } from "@airalogy/shared/locales"
import { computed } from "vue"
import FormOverlay from "./form-overlay.vue"
import PwdLogin from "./pwd-login.vue"
import PwdSignUp from "./pwd-sign-up.vue"

interface IProps {
  type: "login" | "sign-up"
  showOverlay?: boolean
  overlayTitle?: string
  overlayDescription?: string
  overlayButtonText?: string
}

// const userStore = useUserStore()
const props = withDefaults(defineProps<IProps>(), {
  showOverlay: false,
  overlayTitle: undefined,
  overlayDescription: undefined,
  overlayButtonText: undefined,
})
const title = computed(() => {
  const { type } = props
  if (type === "login") {
    return $t("page.login.login.title")
  }
  else if (type === "sign-up") {
    return $t("page.login.register.title")
  }

  return "Welcome to Airalogy"
})

const { routerPushByKey } = useRouterPush()
function handleOverlayButtonClick() {
  routerPushByKey("root")
}
</script>

<style scoped lang="sass">
:deep(.form__title)
  --n-title-font-size: 36px
  font-family: PingFang SC
  line-height: 1
</style>
