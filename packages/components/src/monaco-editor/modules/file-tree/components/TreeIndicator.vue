<template>
  <div
    :dir="direction"
    class="absolute left-1.5 h-full w-[0.5px] rounded-md bg-white/10 py-3 duration-300 ease-in-out rtl:right-1.5 hover:bg-slate-300"
  />
</template>

<script setup lang="ts">
import { useTreeContext } from "../composables/useTreeContext"

const { direction } = useTreeContext()
</script>
