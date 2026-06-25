<template>
  <div class="traceback-repeated-frames">
    <div>{{ terms.similar_frames_skipped }}</div>
    <ul>
      <li v-for="(item, index) in frames" :key="index">
        {{ repeatedFramesDescription(item) }}
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
import { template } from "lodash-es"
import { terms } from "../constants"

defineProps<{
  frames: any[]
}>()

const repeatedFramesDescription = template(terms.repeated_frames_description)
</script>
