import { nanoid } from "nanoid"
import { REG_PHONE } from "../../constants/reg"
import { request } from "../request"

/**
 * Login
 *
 * @param username User name
 * @param password Password
 */
export function fetchLogin(
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
  const { password, email, phone, code, countryCode } = payload
  if (type === "email") {
    return request<Api.Auth.LoginInfo>({
      url: "/signin_by_email",
      method: "POST",
      data: {
        email,
        password,
      },
    })
  }

  if (type === "code") {
    return request<Api.Auth.LoginInfo>({
      url: "/signin",
      method: "POST",
      data: {
        phone,
        country_code: countryCode,
        verify_code: code,
      },
    })
  }

  return request<Api.Auth.LoginInfo>({
    url: "/signin",
    method: "POST",
    data: {
      phone,
      password,
    },
  })
}

/** Get user info */
export function fetchGetUserInfo() {
  return request<Api.Auth.UserInfo>({ url: "/auth/getUserInfo" })
}

/**
 * Refresh token
 *
 * @param refreshToken Refresh token
 */
export function fetchRefreshToken(refreshToken: string) {
  return request<Api.Auth.LoginToken>({
    url: "/auth/refreshToken",
    method: "POST",
    data: {
      refreshToken,
    },
  })
}

export function fetchDebug() {
  return request<string>({
    url: "/debug-post",
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    data: {
      a: "1",
    },
  })
}

export function postSignup(
  type: "phone" | "email",
  payload: {
    username: string
    displayName: string
    phone?: string
    email?: string
    password?: string
    confirmPassword?: string
    code?: string
    countryCode?: string
  },
) {
  const { password, email, phone, confirmPassword, username, code, displayName, countryCode } = payload
  if (type === "email") {
    return request<Api.Auth.LoginInfo>({
      url: "/signup",
      method: "POST",
      data: {
        email,
        password,
        confirm_password: confirmPassword,
        name: displayName,
        username,
      },
    })
  }

  return request<Api.Auth.LoginInfo>({
    url: "/signup",
    method: "POST",
    data: {
      phone,
      email,
      verify_code: code,
      username,
      name: displayName,
      password,
      confirm_password: confirmPassword,
      country_code: countryCode,
    },
  })
}

export function putChangePassword(payload: {
  code: string
  password: string
  confirmPassword: string
}) {
  const { code, confirmPassword, password } = payload
  return request<{ message: string }>({
    url: "/users/change_password",
    method: "PUT",
    data: {
      verify_code: code,
      new_password: password,
      comfirm_password: confirmPassword,
    },
  })
}

export function putChangePhone(payload: {
  currentCode: string
  newCode: string
  newCountryCode?: string
  newPhone: string
}) {
  const { currentCode, newCode, newPhone, newCountryCode } = payload

  if (!currentCode || !newCode || !newPhone || !newCountryCode) {
    throw new Error("Missing required param")
  }

  return request<{ message: string }>({
    url: "/users/change_phone",
    method: "PUT",
    data: {
      new_country_code: newCountryCode.startsWith("+") ? newCountryCode.slice(1) : newCountryCode,
      new_phone: newPhone,
      current_phone_verify_code: currentCode,
      new_phone_verify_code: newCode,
    },
  })
}

export function postSendResetPasswordCode() {
  return request<{ success: boolean }>({
    url: "/users/send_verify_code",
    method: "POST",
    data: {
      type: "reset_password",
    },
  })
}
export function postSendCode(phone: string, dialCode: string, type: "signup" | "signin" | "reset_password" | "change_phone") {
  if (!dialCode) {
    throw new Error("Invalid country code")
  }

  if ((dialCode === "+86" || dialCode === "86") && !REG_PHONE.test(phone)) {
    throw new Error("Invalid phone number")
  }

  if (!type) {
    throw new Error("Invalid type")
  }

  return request<{ success: boolean }>({
    url: "/send_verify_code",
    method: "POST",
    data: {
      type,
      phone,
      country_code: dialCode.startsWith("+") ? dialCode.slice(1) : dialCode,
    },
  })
}

// Send verification code to user's current phone (backend knows the phone number)
export function postSendCodeToCurrentPhone(type: "change_phone") {
  return request<{ success: boolean }>({
    url: "/users/send_verify_code",
    method: "POST",
    data: {
      type,
    },
  })
}
export async function getUserAPIKey() {
  return request<{ api_key: string }>({ url: "/users/api_key", method: "GET" })
}

export async function putGenerateAPIKey() {
  return await request<{ api_key: string }>({
    url: "/users/generate_api_key",
    method: "PUT",
  })
}

export async function checkEmailDuplicate(email: string) {
  if (!email) {
    return { duplicated: false, message: "Email is required" }
  }

  try {
    const { data, error } = await request<{ result: boolean }>({
      method: "POST",
      url: "/signin_by_email",
      data: { email, password: nanoid() },
      metadata: {
        noRetry: true,
        showError: false,
      },
    })

    if (error) {
      throw error
    }

    if (data && data.result) {
      return { duplicated: false, message: "" }
    }

    return { duplicated: false, message: "Email is required" }
  }
  catch (error: any) {
    // If API returns 400 with "Email already exists", it means email is duplicate
    const errorDetail = error?.response?.data?.detail
    if (typeof errorDetail === "string") {
      if (errorDetail.includes("User not found")) {
        return { duplicated: false, message: "" }
      }
      if (errorDetail.includes("The password is incorrect")) {
        return { duplicated: true, message: "Email already exists" }
      }
    }

    // For other errors, log and assume no duplicate (fail safe)
    console.error("Error checking email duplicate:", error)
    return { duplicated: false, message: "" }
  }
}
