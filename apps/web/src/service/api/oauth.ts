import { request } from "../request"

export interface OAuthAuthorizeParams {
  response_type: "code"
  client_id: string
  redirect_uri: string
  state?: string
  scope?: string
  auto_redirect?: boolean
}

export interface OAuthAuthorizeResult {
  code: string
  state?: string
  scope: string
  expires_in: number
  redirect_to: string
}

export function fetchOAuthAuthorize(params: OAuthAuthorizeParams) {
  return request<OAuthAuthorizeResult>({
    url: "/oauth/authorize",
    method: "GET",
    params,
  })
}
