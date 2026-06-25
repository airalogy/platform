<template>
  <n-button
    class="footer__icon ml-5 h-10 w-10 p-1"
    tertiary
    style="--n-color-focus: rgba(255, 255, 255, 0.6)"
    @click="handleOpenTab"
  >
    <template #icon>
      <n-icon :size="24" color="white">
        <logo-github v-if="props.name === 'github'" />
        <logo-facebook v-else-if="props.name === 'facebook'" />
        <logo-wechat v-else-if="props.name === 'wechat'" />
        <logo-twitter v-else-if="props.name === 'twitter'" />
        <global-logo v-else />
      </n-icon>
    </template>
  </n-button>
</template>

<script setup lang="ts">
import LogoFacebook from "~icons/ion/logo-facebook"

import LogoGithub from "~icons/ion/logo-github"
import LogoTwitter from "~icons/ion/logo-twitter"
import LogoWechat from "~icons/ion/logo-wechat"

interface IProps {
  name: "github" | "facebook" | "wechat" | "twitter" | "default"
  to: string
  external?: boolean
}

const props = withDefaults(defineProps<IProps>(), {
  name: "default",
  to: "/",
  external: true,
})
function handleOpenTab() {
  globalThis.open(props.to, "_blank", "noreferrer")
}
</script>

<style scoped lang="sass">
.footer__icon
  padding: 5px
  border-radius: 9px
  background: rgba(255,255,255,0.1)
</style>
