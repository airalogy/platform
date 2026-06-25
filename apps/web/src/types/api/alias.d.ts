declare namespace Api {
  namespace Alias {
    interface AliasFields {
      user_alias?: string | null
      lab_alias?: string | null
    }

    interface UserAlias {
      id: string
      user_alias?: string | null
      lab_alias?: string | null
      alias?: string | null
    }
  }
}
