declare namespace Api {
  namespace Auth {
    interface LoginInfo {
      token: string
      user: UserInfo
    }

    interface LoginToken {
      token: string
      refreshToken?: string | null
    }

    interface UserInfo {
      id: string
      bio?: string
      username: string
      name: string
      updated_at: string
      phone?: string | null
      country_code?: string | null
      email: string | null
      roles?: string[]
      avatar?: string | null
      avatar_url?: string | null
      level: number
    }
  }
}
