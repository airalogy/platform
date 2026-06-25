<!-- eslint-disable vue/component-name-in-template-casing -->
<template>
  <AIRALayout
    ref="wrapperRef"
    v-model:sider-collapse="appStore.siderCollapse"
    class="h-screen"
    :mode="layoutMode"
    scroll-mode="wrapper"
    :is-mobile="appStore.isMobile"
    :full-content="appStore.fullContent"
    :fixed-top="themeStore.fixedHeaderAndTab"
    :header-class="props.headerClass"
    :header-height="themeStore.header.height"
    :tab-visible="themeStore.tab.visible"
    :tab-height="themeStore.tab.height"
    :content-class="
      [
        'mx-auto w-full bg-layout',
        appStore.contentXScrollable ? 'overflow-x-hidden' : '',
        props.contentClass,
      ]
    "
    :sider-visible="true"
    :sider-width="siderWidth"
    :sider-collapsed-width="siderCollapsedWidth"
    :footer-visible="themeStore.footer.visible"
    :fixed-footer="themeStore.footer.fixed"
    :right-footer="themeStore.footer.right"
    :float-button-props="props.floatButtonProps"
    :is-container="!route.meta.notContainer"
  >
    <template #header>
      <chat-header />
    </template>
    <template #sider>
      <chat-menu />
    </template>
    <slot>
      <global-content v-if="appStore.isSpinWrapper" :container-content-class="themeStore.content.containerContentClass" :content-class="themeStore.content.contentClass" :show-spin="true" />
      <global-content v-else />
    </slot>

    <template v-if="$slots.floatButton" #floatButton>
      <slot name="floatButton" />
    </template>
  </AIRALayout>
</template>

<script setup lang="ts">
import type { LayoutMode } from "@/types/layout"
import type { FloatButtonProps } from "naive-ui"
import AIRALayout from "@/layouts/base-layout/index.vue"
import GlobalContent from "@/layouts/modules/global-content/index.vue"
import { useAppStore } from "@/store/modules/app"
import { useThemeStore } from "@airalogy/composables/theme"
import { storeToRefs } from "pinia"
import { render } from "vue"
import ChatHeader from "./chat-header.vue"
import ChatMenu from "./chat-menu.vue"

defineOptions({
  name: "ChatLayout",
})

const props = defineProps<IProps>()
interface IProps {
  floatButtonProps?: FloatButtonProps
  contentClass?: string
  headerClass?: string
}
const appStore = useAppStore()
const themeStore = useThemeStore()

const wrapperRef = ref<HTMLElement | null>(null)
const { popoverFloating, popoverComponent, floatingStyles, popoverReference } = storeToRefs(appStore)

const layoutMode = computed(() => {
  const vertical: LayoutMode = "vertical"
  const horizontal: LayoutMode = "horizontal"
  return themeStore.layout.mode.includes(vertical) ? vertical : horizontal
})

const headerPropsConfig: Record<UnionKey.ThemeLayoutMode, App.Global.HeaderProps> = {
  "vertical": {
    showLogo: false,
    showMenu: false,
    showMenuToggler: true,
  },
  "vertical-mix": {
    showLogo: false,
    showMenu: false,
    showMenuToggler: false,
  },
  "horizontal": {
    showLogo: true,
    showMenu: true,
    showMenuToggler: false,
  },
  "horizontal-mix": {
    showLogo: true,
    showMenu: true,
    showMenuToggler: false,
  },
}

const headerProps = computed(() => headerPropsConfig[themeStore.layout.mode])

const isVerticalMix = computed(() => themeStore.layout.mode === "vertical-mix")

const isHorizontalMix = computed(() => themeStore.layout.mode === "horizontal-mix")

const siderWidth = computed(() => getSiderWidth())

const siderCollapsedWidth = computed(() => getSiderCollapsedWidth())

function getSiderWidth() {
  const { width, mixWidth, mixChildMenuWidth } = themeStore.sider

  let w = isVerticalMix.value || isHorizontalMix.value ? mixWidth : width

  if (isVerticalMix.value && appStore.mixSiderFixed) {
    w += mixChildMenuWidth
  }

  return w
}

function getSiderCollapsedWidth() {
  const { collapsedWidth, mixCollapsedWidth, mixChildMenuWidth } = themeStore.sider

  let w = isVerticalMix.value || isHorizontalMix.value ? mixCollapsedWidth : collapsedWidth

  if (isVerticalMix.value && appStore.mixSiderFixed) {
    w += mixChildMenuWidth
  }

  return w
}

onMounted(() => {
  popoverReference.value = unrefElement(wrapperRef) || null
})

onUnmounted(() => {
  popoverReference.value = null
})

watch(() => popoverComponent.value?.renderedComponent?.vNode, (component) => {
  const el = unrefElement(popoverFloating.value)
  if (el && component) {
    render(component, el)
  }
}, { flush: "post" })

const route = useRoute()

watch(() => route.meta.reload, async (val) => {
  if (val) {
    await appStore.reloadPage(10)
    route.meta.reload = false
  }
})
</script>

<style lang="sass" scoped>
.admin-content
  @apply bg-gray-50

.admin-header
  @apply border-b border-gray-200
</style>

<style lang="sass">
html, body, #app
  height: 100%
</style>
