import { getUserByUsername, getUserInfoById } from "@/service/api/users"

const AIRALOGY_USER_PREFIX = "airalogy.id.user."

export function normalizeAiralogyUserId(rawId: string) {
  if (!rawId) {
    return ""
  }
  if (rawId.startsWith(AIRALOGY_USER_PREFIX)) {
    return rawId.slice(AIRALOGY_USER_PREFIX.length)
  }
  return rawId
}

export async function resolveAiralogyUser(rawId: string) {
  const normalizedId = normalizeAiralogyUserId(rawId)
  if (!normalizedId) {
    return { user: null, normalizedId: "" }
  }

  try {
    if (/^\d+$/.test(normalizedId)) {
      const { data } = await getUserInfoById(normalizedId)
      return { user: data || null, normalizedId }
    }

    const user = await getUserByUsername(normalizedId)
    return { user: user || null, normalizedId }
  }
  catch (e) {
    return { user: null, normalizedId }
  }
}
