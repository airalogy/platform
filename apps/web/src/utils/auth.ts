function isLoggedIn() {
  const token = localStorage.getItem("user-token")
  return Boolean(token)
}

function getAuthToken() {
  const token = localStorage.getItem("user-token")
  return token ? `${token}` : null
}

function setAuthToken(token: string) {
  return localStorage.setItem("user-token", token)
}

function clearAuth() {
  localStorage.removeItem("user-session")
  localStorage.removeItem("user-token")
}

export { clearAuth, getAuthToken, isLoggedIn, setAuthToken }
