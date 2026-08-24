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
    lab_structure_mode: singleLab ? "structured" : "flat",
    documentation_profile: singleLab ? "customer_managed" : "community",
    documentation_url: "/docs/",
    support_url: "",
    ai_enabled: false,
    sms_login_enabled: false,
    sms_signup_required: false,
    enabled_chat_models: [],
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
  const isStructuredLab = computed(() => status.value.lab_structure_mode === "structured")
  const documentationProfile = computed(() => status.value.documentation_profile)
  const documentationUrl = computed(() => status.value.documentation_url)
  const supportUrl = computed(() => status.value.support_url)
  const aiEnabled = computed(() => status.value.ai_enabled)
  const smsLoginEnabled = computed(() => status.value.sms_login_enabled === true)
  const smsSignupRequired = computed(() => status.value.sms_signup_required === true)
  const enabledChatModels = computed(() => status.value.enabled_chat_models ?? [])

  async function load() {
    loaded.value = false
    try {
      const { data, error } = await fetchInstanceStatus()
      if (data) {
        status.value = data
        loadError.value = typeof data.sms_signup_required === "boolean"
          ? null
          : new Error("Instance signup capability is unavailable")
      }
      else if (error) {
        loadError.value = error
        status.value.sms_login_enabled = false
        status.value.sms_signup_required = false
      }
    }
    catch (error) {
      loadError.value = error
      status.value.sms_login_enabled = false
      status.value.sms_signup_required = false
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
    isStructuredLab,
    documentationProfile,
    documentationUrl,
    supportUrl,
    aiEnabled,
    smsLoginEnabled,
    smsSignupRequired,
    enabledChatModels,
    load,
  }
})
