<!-- eslint-disable vue/component-name-in-template-casing -->
<template>
  <AIRALayout
    ref="wrapperRef"
    v-model:sider-collapse="appStore.siderCollapse"
    :class="layoutClass"
    :mode="layoutMode"
    :scroll-el-id="LAYOUT_SCROLL_EL_ID"
    :scroll-mode="layoutScrollMode"
    :is-mobile="appStore.isMobile"
    :full-content="appStore.fullContent"
    :fixed-top="themeStore.fixedHeaderAndTab"
    :header-height="themeStore.header.height"
    :tab-visible="themeStore.tab.visible"
    :tab-height="themeStore.tab.height"
    :content-class="
      [
        'mx-auto w-full bg-layout',
        appStore.contentXScrollable ? 'overflow-x-hidden' : '',
        contentOverflowClass,
        props.contentClass,
      ]
    "
    :sider-visible="siderVisible"
    :sider-width="siderWidth"
    :sider-collapsed-width="siderCollapsedWidth"
    :footer-visible="themeStore.footer.visible && !route.meta.hideFooter"
    :fixed-footer="themeStore.footer.fixed"
    :right-footer="themeStore.footer.right"
    :float-button-props="props.floatButtonProps"
    :is-container="!route.meta.notContainer"
    footer-class="bg-[#2B2B38]"
    header-class="bg-[#2B2B38]"
  >
    <template #header>
      <global-header v-bind="headerProps" :is-container="!route.meta.notContainer" :class="props.headerClass" />
    </template>
    <slot>
      <global-content v-if="appStore.isSpinWrapper" :container-content-class="themeStore.content.containerContentClass" :content-class="themeStore.content.contentClass" :show-spin="true" />
      <global-content v-else />
    </slot>
    <template v-if="!route.meta.hideFooter" #footer>
      <global-footer />
    </template>
    <template v-if="$slots.floatButton" #floatButton>
      <slot name="floatButton" />
    </template>
    <div v-if="popoverComponent" ref="popoverFloating" :style="floatingStyles" class="z-9999 pt-2" />
  </AIRALayout>
</template>

<script setup lang="ts">
import type { LayoutMode } from "@/types/layout"
import type { FloatButtonProps } from "naive-ui"
import AIRALayout from "@/layouts/base-layout/index.vue"

import { LAYOUT_SCROLL_EL_ID } from "@/layouts/base-layout/utils/shared"
import GlobalHeader from "@/layouts/modules/global-header/index.vue"
import { useAppStore } from "@/store/modules/app"
import { useThemeStore } from "@airalogy/composables/theme"
import { storeToRefs } from "pinia"
import { render } from "vue"
import GlobalContent from "../modules/global-content/index.vue"
import GlobalFooter from "../modules/global-footer/index.vue"

defineOptions({
  name: "GlobalLayout",
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

const siderVisible = computed(() => themeStore.layout.mode !== "horizontal")

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

const route = useRoute()
const layoutScrollMode = computed(() => route.meta.scrollMode ?? themeStore.layout.scrollMode)
const layoutClass = computed(() => (route.meta.layoutFullHeight ? "h-screen overflow-hidden" : ""))
const contentOverflowClass = computed(() => (route.meta.disableContentScroll ? "!overflow-y-hidden min-h-0" : ""))

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

watch(() => route.meta.reload, async (val) => {
  if (val) {
    await appStore.reloadPage(10)
    route.meta.reload = false
  }
})
</script>

<style lang="sass"></style>
