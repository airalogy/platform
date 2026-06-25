import { request } from "../request"

export async function putUserProfile(payload: { avatar?: File | null, name?: string, email?: string, bio?: string }) {
  const { avatar, name, email, bio } = payload

  // Trim bio if provided
  const trimmedBio = bio?.trim()

  if (!name && !avatar && !email && !trimmedBio) {
    throw new Error("at least one field is required")
  }

  const formData = new FormData()

  if (avatar) {
    formData.append("avatar_file", avatar)
  }

  if (name) {
    formData.append("name", name)
  }

  if (email) {
    formData.append("email", email)
  }

  // Only append bio if it has content (minLength: 1 from server)
  if (trimmedBio) {
    formData.append("bio", trimmedBio)
  }

  const { data, error } = await request<Api.Auth.UserInfo>({
    url: "/users/update_profile",
    method: "PUT",
    data: formData,
  })

  if (!error && data) {
    return data
  }

  return null
}
