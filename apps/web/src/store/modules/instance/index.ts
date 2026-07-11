import { SetupStoreId } from "@/enum"
import { fetchInstanceStatus, type InstanceStatus } from "@/service/api/instance"
import { defineStore } from "pinia"

function fallbackStatus(): InstanceStatus {
  const singleLab = import.meta.env.VITE_DEPLOYMENT_MODE === "single_lab"
  return {
    deployment_mode: singleLab ? "single_lab" : "community",
    single_lab: singleLab,
    initialized: !singleLab,
    signup_mode: singleLab ? "invite_only" : "open",
    bootstrap_token_required: false,
    site_url: window.location.origin,
    lab: null,
  }
}

export const useInstanceStore = defineStore(SetupStoreId.INSTANCE, () => {
  const status = ref<InstanceStatus>(fallbackStatus())
  const loaded = ref(false)
  const loadError = ref<unknown>(null)

  const isSingleLab = computed(() => status.value.single_lab)
  const initialized = computed(() => status.value.initialized)
  const signupMode = computed(() => status.value.signup_mode)
  const lab = computed(() => status.value.lab)

  async function load() {
    try {
      const { data, error } = await fetchInstanceStatus()
      if (data) {
        status.value = data
        loadError.value = null
      }
      else if (error) {
        loadError.value = error
      }
    }
    catch (error) {
      loadError.value = error
    }
    finally {
      loaded.value = true
    }
  }

  return {
    status,
    loaded,
    loadError,
    isSingleLab,
    initialized,
    signupMode,
    lab,
    load,
  }
})
