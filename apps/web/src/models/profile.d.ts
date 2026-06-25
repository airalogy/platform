declare namespace Api {
  namespace Profile {
    interface User extends Api.Alias.AliasFields {
      email: string
      id: string
      updated_at: string
      username: string
      name: string
      avatar: string
      avatar_url: string
      bio?: string
      alias?: string | null
    }
  }
}
