<template>
  <section class="mx-auto h-[70px] flex items-center justify-end" :class="isContainer ? 'container' : ''">
    <global-menu v-if="authStore.isLogin" :button-theme-overrides="{}" label="More" class="mr-3" />
    <!-- <n-dropdown v-if="isMobile" :options="options" @select="handleSelect" /> -->
    <n-dropdown v-if="isMobile" :options="options" @select="handleSelect">
      <n-button quaternary>
        <template #icon>
          <n-icon>
            <icon-tabler-menu-2 />
          </n-icon>
        </template>
      </n-button>
    </n-dropdown>
    <template v-else>
      <template v-if="authStore.isLogin">
        <user-avatar :button-theme-overrides="{}" />
      </template>
      <template v-else>
        <n-button
          class="mr-4"
          quaternary
          @click="routerPushByKey('login')"
        >
          Log in
        </n-button>
        <n-button type="primary" @click="routerPushByKey('sign-up')">
          Sign up
        </n-button>
      </template>
    </template>
  </section>
</template>

<script setup lang="ts">
import type { DropdownOption } from "naive-ui"

import { useBasicLayout } from "@/composables"
import { useRouterPush } from "@/composables/useRouterPush"
import UserAvatar from "@/layouts/modules/global-header/components/user-avatar.vue"
import GlobalMenu from "@/layouts/modules/global-menu/index.vue"
import { useAuthStore } from "@/store/modules/auth"

defineOptions({ name: "GlobalHeader" })

const props = withDefaults(defineProps<IProps>(), {
  showLogo: true,
  showMenu: false,
  showMenuToggler: false,
})

const { isMobile } = useBasicLayout()
interface IProps {
  showLogo?: boolean
  showMenu?: boolean
  showMenuToggler?: boolean
  isContainer?: boolean
}

const authStore = useAuthStore()
const { routerPushByKey } = useRouterPush()
const options: DropdownOption[] = [
  {
    label: "Login",
    key: "login",
    props: {
      onClick: () => {
        routerPushByKey("login")
      },
    },
  },
  {
    label: "Sign up",
    key: "sign-up",
    props: {
      onClick: () => {
        routerPushByKey("sign-up")
      },
    },
  },
]

function handleSelect(key: string) {
  console.log(key)
}
</script>

<style scoped lang="sass"></style>
