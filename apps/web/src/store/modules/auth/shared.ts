import { localStg } from "@/utils/storage"

/** Get token */
export function getToken() {
  return localStg.get("token") || ""
}

/** Get user info */
export function getUserInfo() {
  const emptyInfo: Api.Auth.UserInfo = {
    id: "",
    username: "unknown",
    name: "",
    email: null,
    phone: null,
    avatar: null,
    avatar_url: null,
    roles: [],
    updated_at: "",
    level: 1,
  }
  const userInfo = localStg.get("userInfo") || emptyInfo

  return userInfo
}

/** Clear auth storage */
export function clearAuthStorage() {
  localStg.remove("token")
  localStg.remove("refreshToken")
  localStg.remove("userInfo")
}
