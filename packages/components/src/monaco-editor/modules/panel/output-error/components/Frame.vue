<template>
  <div class="traceback-frame">
    <div v-if="frame.name !== '<module>'" class="traceback-frame-name">
      {{ frame.name }}:
    </div>
    <table class="traceback-lines-table">
      <tbody>
        <tr v-for="line in frame.lines" :key="line.lineno">
          <td class="traceback-lineno">
            {{ line.lineno }}
          </td>
          <td class="traceback-line-content codehilite" v-html="line.text" />
        </tr>
      </tbody>
    </table>
    <table class="traceback-variables-table">
      <tbody>
        <tr v-for="(variable, index) in frame.variables" :key="index">
          <td class="traceback-variable-name codehilite" v-html="variable.name" />
          <td class="traceback-variable-value codehilite" v-html="variable.value" />
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  frame: any
}>()
</script>
