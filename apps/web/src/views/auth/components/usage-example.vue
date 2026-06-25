<template>
  <div class="min-h-screen flex items-center justify-center bg-slate-100">
    <user-form
      type="login"
      :show-overlay="showOverlay"
      overlay-title="Coming Soon"
      overlay-description="Our login system is currently under maintenance. Please check back later."
      overlay-button-text="Understand"
      @overlay:button-click="hideOverlay"
    />
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue"
import UserForm from "./user-form.vue"

const showOverlay = ref(true)

function hideOverlay() {
  showOverlay.value = false
}
</script>
