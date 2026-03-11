// Shared user-facing network/error messages for auth-related flows.

export const SUPPORT_EMAIL = 'dcs@psych.gatech.edu'
export const CONTACT_SUPPORT = `Please contact ${SUPPORT_EMAIL}.`
export const NETWORK_UNAVAILABLE = `Unable to reach server. ${CONTACT_SUPPORT}`
export const SIGNIN_UNAVAILABLE = `Unable to sign in right now. ${CONTACT_SUPPORT}`
export const REGISTRATION_FAILED = `Registration failed. ${CONTACT_SUPPORT}`
export const SERVER_ERROR = `Server error. ${CONTACT_SUPPORT}`

export async function extractDetail(response: Response): Promise<string | undefined> {
  const body = await response.json().catch(() => ({}))
  return typeof body?.detail === 'string' ? body.detail : undefined
}
