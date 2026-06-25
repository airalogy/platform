<template>
  <n-popover
    :show="isShow"
    :show-arrow="false"
    placement="bottom-start"
    @clickoutside="handleClickOutside"
  >
    <template #trigger>
      <n-button
        :theme-overrides="props.buttonThemeOverrides"
        class="h-[36px] rounded-2 px-3"
        icon-placement="right"
        v-bind="$attrs"
        @click="showDropdown"
      >
        <span class="mr-2 text-4"> {{ labelText }} </span>
        <template #icon>
          <dropdown-icon filled :expended="isShow" />
        </template>
      </n-button>
    </template>

    <div class="menu__popover">
      <div class="menu__list">
        <n-button
          v-for="item in menuItems"
          :key="item.name"
          text
          class="menu__item"
          @click="handleNavigate(item.name)"
        >
          {{ item.label }}
        </n-button>
      </div>
    </div>
  </n-popover>
</template>

<script setup lang="tsx">
import type { ButtonProps } from "naive-ui"

import { useBoolean } from "@/composables"
import { useRouterPush } from "@/composables/useRouterPush"
import { $t } from "@airalogy/shared/locales"
import { buttonThemeOverrides } from "../global-header/constants"

defineOptions({ name: "GlobalMenu" })

const props = withDefaults(
  defineProps<IProps>(),
  {
    buttonThemeOverrides: () => ({ ...buttonThemeOverrides }),
    label: "",
  },
)
const emits = defineEmits<IEmits>()

interface IProps {
  buttonThemeOverrides?: ButtonProps["themeOverrides"]
  label?: string
}

interface IEmits {
  (e: "modal:open"): void
  (e: "search:start-loading"): void
  (e: "search:end-loading"): void
}

interface MenuItem {
  name: App.Global.RouteNameKey
  label: string
}

const { bool: isShow, setFalse: hideDropdown, setTrue: showDropdown } = useBoolean()

const labelText = computed(() => props.label || $t("common.my"))

const menuItems = computed<MenuItem[]>(() => ([
  { name: "labs-my", label: $t("common.labsLabel") },
  { name: "project-dashboard", label: $t("common.projectsLabel") },
  { name: "protocols-my", label: $t("common.protocolsLabel") },
]))

const { routerPushByKey } = useRouterPush()

function handleNavigate(name: App.Global.RouteNameKey) {
  routerPushByKey(name)
  hideDropdown()
}

function handleClickOutside() {
  hideDropdown()
}
</script>

<style scoped lang="sass">
@use "@styles/sass/tab.sass" as *

.menu__popover
  padding: 6px 4px

.menu__list
  display: flex
  flex-direction: column
  gap: 4px
  min-width: 10rem

.menu__item
  justify-content: flex-start
  width: 100%
  height: 32px
  padding: 0 12px
  border-radius: 6px
  font-size: 14px

.menu__item:hover
  background: #EDEFF4
</style>
