import type { PiniaStore } from "@airalogy/shared/types"
import { useRouterPush } from "@/composables/useRouterPush"

import { SetupStoreId } from "@/enum"
import { getCachedAttachment } from "@/service/api/attachments"
import { fetchGetUserInfo, fetchLogin, postSignup, putChangePassword, putChangePhone } from "@/service/api/auth"
import { localStg, localStgWithExpire } from "@/utils/storage"
import { $t } from "@airalogy/shared/locales"
import { defineStore } from "pinia"
import { computed, nextTick, reactive, ref } from "vue"
import { useRouteStore } from "../route"
import { clearAuthStorage, getToken, getUserInfo } from "./shared"

export const useAuthStore = defineStore(SetupStoreId.AUTH, () => {
  const routeStore = useRouteStore()
  const { route, toRoot, redirectFromLogin } = useRouterPush(false)
  const loginLoading = ref(false)
  const startLoading = () => (loginLoading.value = true)
  const endLoading = () => (loginLoading.value = false)

  const token = ref(getToken())

  const userInfo = reactive(getUserInfo())

  /** Computed dial code from user info */
  const dialCode = computed(() => userInfo.country_code || "")

  /** Is login */
  const isLogin = computed(() => Boolean(token.value))
  const justSignedUp = ref(Boolean(sessionStorage.getItem("justSignedUp")))

  /** Reset auth store */
  async function resetStore() {
    const authStore = useAuthStore()

    clearAuthStorage()
    authStore.$reset()
    token.value = ""

    if (!route.value.meta.constant) {
      await toRoot()
    }

    routeStore.resetStore()
  }

  /**
   * Login
   *
   * @param username User name
   * @param password Password
   */
  async function login(
    type: "phone" | "email" | "code",
    payload: Partial<{
      username: string
      phone: string
      countryCode: string
      email: string
      password: string
      token: string
      code: string
    }>,
  ) {
    startLoading()

    const response = await fetchLogin(type, payload)

    const { data: loginInfo, error } = response

    if (loginInfo) {
      const pass = loginByInfo(loginInfo)
      if (pass) {
        routeStore.initAuthRoute()

        // Wait for next tick to ensure route is initialized
        await nextTick()

        await redirectFromLogin()

        if (routeStore.isInitAuthRoute) {
          window.$notification?.success({
            title: $t("page.login.common.loginSuccess"),
            content: $t("page.login.common.welcomeBack", {
              username: userInfo.name || userInfo.username,
            }),
            duration: 4500,
          })
        }
      }
    }
    else {
      await resetStore()
    }

    endLoading()
  }
  function loginByInfo(loginInfo: Api.Auth.LoginInfo) {
    const { token: authToken, user } = loginInfo
    // 1. stored in the localStorage, the later requests need it in headers
    localStgWithExpire.set("token", authToken)
    // localStg.set("refreshToken", loginToken.refreshToken)

    if (user) {
      // 2. store user info
      localStgWithExpire.set("userInfo", user)

      // 3. update auth route
      token.value = authToken
      Object.assign(userInfo, user)

      return true
    }

    return false
  }
  async function loginByToken(loginToken: Api.Auth.LoginToken) {
    // 1. stored in the localStorage, the later requests need it in headers
    localStgWithExpire.set("token", loginToken.token)
    // localStg.set("refreshToken", loginToken.refreshToken)

    const { data: info, error } = await fetchGetUserInfo()

    if (!error) {
      // 2. store user info
      localStgWithExpire.set("userInfo", info)

      // 3. update auth route
      token.value = loginToken.token
      Object.assign(userInfo, info)

      return true
    }

    return false
  }

  function logout() {
    window.$dialog?.info({
      title: $t("common.tip"),
      content: $t("common.logoutConfirm"),
      positiveText: $t("common.confirm"),
      negativeText: $t("common.cancel"),
      onPositiveClick: async () => {
        await resetStore()
      },
    })
  }

  /**
   * signup
   *
   * @param username User name
   * @param password Password
   */
  async function signup(
    type: "phone" | "email",
    payload: {
      username: string
      displayName: string
      phone?: string
      email?: string
      password: string
      confirmPassword: string
      code?: string
      countryCode?: string
    },
  ) {
    try {
      startLoading()

      const response = await postSignup(type, payload)

      const { data: loginInfo, error } = response

      if (loginInfo) {
        const pass = loginByInfo(loginInfo)
        if (pass) {
        // Set flag to show testing notification on home page
          justSignedUp.value = true
          sessionStorage.setItem("justSignedUp", "true")
          routeStore.initAuthRoute()

          await redirectFromLogin()

          if (routeStore.isInitAuthRoute) {
            window.$notification?.success({
              title: $t("page.login.common.signupSuccess"),
              content: $t("page.login.common.welcome", {
                username: userInfo.name || userInfo.username,
              }),
              duration: 4500,
            })
          }
        }
        return true
      }
      else {
        await resetStore()
        return error
      }
    }
    catch (error) {
      console.log(error)
      return error
    }
    finally {
      endLoading()
    }
  }

  async function changePassword(payload: {
    code: string
    password: string
    confirmPassword: string
  }) {
    startLoading()

    const response = await putChangePassword(payload)

    const { data, error } = response

    if (data) {
      if (data.message === "success") {
        routeStore.initAuthRoute()

        await redirectFromLogin()

        if (routeStore.isInitAuthRoute) {
          window.$notification?.success({
            title: $t("page.login.common.signupSuccess"),
            content: $t("page.login.common.welcome", {
              username: userInfo.name || userInfo.username,
            }),
            duration: 4500,
          })
        }
      }
    }
    else {
      await resetStore()
    }

    endLoading()
  }

  async function changePhone(payload: {
    currentCode: string
    newCode: string
    newCountryCode?: string
    newPhone: string
  }) {
    startLoading()

    const response = await putChangePhone(payload)

    const { data, error } = response

    if (data) {
      if (data.message === "success") {
        // Refresh user info
        const { data: info, error: infoError } = await fetchGetUserInfo()
        if (!infoError) {
          localStgWithExpire.set("userInfo", info)
          Object.assign(userInfo, info)
          window.$notification?.success({
            title: "Success",
            content: "Phone number changed successfully.",
            duration: 4500,
          })
        }
      }
    }
    else {
      // Handle error, maybe just log it and the message will be shown by the request handler
      console.error("Failed to change phone number", error)
    }

    endLoading()
  }

  async function updateUserInfo() {
    const { data: info, error: infoError } = await fetchGetUserInfo()
    if (!infoError) {
      localStgWithExpire.set("userInfo", info)
      Object.assign(userInfo, info)
    }
  }

  async function getUserAvatar() {
    const { avatar } = userInfo

    if (!avatar) {
      return
    }

    const attachment = await getCachedAttachment(avatar)
    if (attachment) {
      Object.assign(userInfo, {
        avatar_url: attachment.url,
      })

      localStg.set("userInfo", userInfo)
    }
  }

  function clearSignupFlag() {
    justSignedUp.value = false
    sessionStorage.removeItem("justSignedUp")
  }

  return {
    token,
    userInfo,
    dialCode,
    isLogin,
    loginLoading,
    justSignedUp,
    resetStore,
    login,
    logout,
    signup,
    changePassword,
    changePhone,
    updateUserInfo,
    getUserAvatar,
    clearSignupFlag,
  }
})

export type AuthStoreState = PiniaStore<typeof useAuthStore>
