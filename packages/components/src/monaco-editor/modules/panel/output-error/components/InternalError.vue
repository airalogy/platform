<template>
  <div>
    <p>{{ startMessage }}</p>
    <ul>
      <li v-for="suggestion in suggestions" :key="suggestion">
        {{ suggestion }}
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
import { template } from "lodash-es"
import { computed } from "vue"
import { terms } from "../constants"

const props = defineProps<{
  ranCode: boolean
  canGiveFeedback: boolean
}>()

const startMessage = computed(() => {
  const maybeErrorReported = props.canGiveFeedback ? terms.error_has_been_reported : ""
  return template(terms.internal_error_start)({ maybeErrorReported })
})

const suggestions = computed(() => {
  const suggestionList = []
  if (props.ranCode) {
    suggestionList.push(terms.try_running_code_again)
  }
  suggestionList.push(
    terms.refresh_and_try_again,
    terms.try_using_different_browser,
  )
  if (props.canGiveFeedback) {
    suggestionList.push(terms.give_feedback_from_menu)
  }
  return suggestionList
})
</script>
