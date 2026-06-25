<template>
  <template v-if="!props.fullScreen && !props.docked">
    <slot />
  </template>

  <Teleport v-else to="body">
    <slot v-bind="{ contentClass }" />
  </Teleport>
</template>

<script setup lang="ts">
interface Props {
  fullScreen: boolean
  docked: boolean
}

const props = defineProps<Props>()
const contentClass = computed(() => {
  if (props.fullScreen) {
    return "chat__wrapper--full-screen"
  }
  return "chat__wrapper--docked"
})
</script>

<style lang="sass">
.chat__wrapper--full-screen, .chat__wrapper--docked
  @apply fixed bg-white z-1999

.chat__wrapper--full-screen
  @apply left-0 top-0 right-0 bottom-0
  .chat__content, .chat__footer
    max-width: 1080px
    @apply mx-auto w-full

.chat__wrapper--docked
  @apply shadow-lg rounded-lg bg-white overflow-hidden
  min-width: 350px
  min-height: 400px
  max-width: 800px
  max-height: 80vh
  width: 450px
  height: 600px
  resize: both
</style>
