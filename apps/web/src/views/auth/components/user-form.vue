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
      <n-tabs
        v-if="instanceStore.smsLoginEnabled"
        v-model:value="activeTab"
        class="card-tabs"
        size="large"
        animated
        pane-wrapper-style="margin: 0 -4px"
        pane-style="padding-left: 4px; padding-right: 4px; padding-top: 36px; box-sizing: border-box;"
        tab-style="text-transform: capitalize;"
      >
        <n-tab-pane name="verification" :tab="$t('page.login.codeLogin.title')" display-directive="show">
          <code-login />
        </n-tab-pane>
        <n-tab-pane name="email" :tab="$t('page.login.emailLogin.title')" display-directive="show">
          <pwd-login />
        </n-tab-pane>
      </n-tabs>
      <pwd-login v-else />
    </template>
    <template v-else>
      <div v-if="!instanceStore.loaded" class="flex justify-center py-12">
        <n-spin size="large" />
      </div>
      <n-result
        v-else-if="instanceStore.loadError"
        status="error"
        :title="$t('page.login.register.serviceUnavailableTitle')"
        :description="$t('page.login.register.serviceUnavailableHelper')"
      >
        <template #footer>
          <n-button type="primary" @click="instanceStore.load">
            {{ $t("page.login.register.retry") }}
          </n-button>
        </template>
      </n-result>
      <phone-sign-up v-else-if="instanceStore.smsSignupRequired" />
      <pwd-sign-up v-else />
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
import { useInstanceStore } from "@/store/modules/instance"
import { $t } from "@airalogy/shared/locales"
import { computed, ref } from "vue"
import CodeLogin from "./code-login.vue"
import FormOverlay from "./form-overlay.vue"
import PhoneSignUp from "./phone-sign-up.vue"
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
const instanceStore = useInstanceStore()
const activeTab = ref("verification")
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

:deep(.n-tabs-bar)
  height: 4px
  border-radius: 10px
.card-tabs .n-tabs-nav--bar-type
  padding-left: 4px
</style>
