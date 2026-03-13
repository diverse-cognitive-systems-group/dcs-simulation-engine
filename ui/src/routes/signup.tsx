// Registration page at /signup. Collects participant info, validates with Zod,
// and on success shows a one-time access key that the user must copy before continuing.

import { createRoute, Link, useNavigate } from '@tanstack/react-router'
import { useState } from 'react'
import { z } from 'zod'
import { ThemeToggle } from '@/components/theme-toggle'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import {
  extractDetail,
  NETWORK_UNAVAILABLE,
  REGISTRATION_FAILED,
  SERVER_ERROR,
} from '@/lib/api-errors'
import { rootRoute } from './__root'

// Zod schema defines the shape and validation rules for the form.
// safeParse() is called on every render so fieldErrors stays up to date as the user types.
const schema = z.object({
  full_name: z.string().min(1, 'Required'),
  email: z.string().email('Enter a valid email address'),
  phone_number: z
    .string()
    .transform((v) => v.replace(/\D/g, ''))
    .pipe(z.string().min(10, 'Enter at least 10 digits')),
  prior_experience: z.string().min(1, 'Required'),
  additional_comments: z.string(),
  consent_to_followup: z.boolean(),
  consent_signature: z.string().min(1, 'Required'),
})

// Signature validation is separate because it depends on another field (full_name),
// which Zod's static schema can't reference directly.
function makeSignatureSchema(fullName: string) {
  return z.string().refine((v) => v.trim() === fullName.trim(), {
    message: 'Signature must match your full name exactly',
  })
}

type FormFields = keyof typeof schema.shape

interface RegistrationResponse {
  player_id: string
  api_key: string
}

async function registerPlayer(body: object): Promise<RegistrationResponse> {
  let res: Response
  try {
    res = await fetch('/api/player/registration', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
  } catch {
    throw new Error(NETWORK_UNAVAILABLE)
  }
  if (!res.ok) {
    const detail = await extractDetail(res)
    if (res.status >= 500) {
      throw new Error(SERVER_ERROR)
    }
    throw new Error(detail ?? REGISTRATION_FAILED)
  }
  return res.json()
}

/** Renders a validation error below a field, or nothing if there is no error. */
function FieldError({ msg }: { msg?: string }) {
  if (!msg) return null
  return <p className="text-xs text-destructive">{msg}</p>
}

function SignupPage() {
  const navigate = useNavigate()
  const [form, setForm] = useState({
    full_name: '',
    email: '',
    phone_number: '',
    prior_experience: '',
    additional_comments: '',
    consent_to_followup: false,
    consent_signature: '',
  })
  // touched tracks which fields the user has interacted with so we only show errors
  // after they've left a field, not on initial load.
  const [touched, setTouched] = useState<Partial<Record<FormFields, boolean>>>({})
  const [consentRead, setConsentRead] = useState(false)
  const [consentScrolledToBottom, setConsentScrolledToBottom] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  // issuedKey is set after successful registration; its presence switches the page
  // to the "copy your key" view instead of the form.
  const [issuedKey, setIssuedKey] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  function set(field: string, value: string | boolean) {
    setForm((prev) => ({ ...prev, [field]: value }))
  }

  function touch(field: FormFields) {
    setTouched((prev) => ({ ...prev, [field]: true }))
  }

  const parsed = schema.safeParse(form)
  const fieldErrors: Partial<Record<FormFields, string>> = {}
  if (!parsed.success) {
    for (const issue of parsed.error.issues) {
      const field = issue.path[0] as FormFields
      if (!fieldErrors[field]) fieldErrors[field] = issue.message
    }
  }

  const sigError =
    touched.consent_signature && form.consent_signature
      ? makeSignatureSchema(form.full_name).safeParse(form.consent_signature).error?.issues[0]
          ?.message
      : undefined

  function visibleError(field: FormFields) {
    if (field === 'consent_signature')
      return sigError ?? (touched[field] ? fieldErrors[field] : undefined)
    return touched[field] ? fieldErrors[field] : undefined
  }

  const sigValid =
    !form.full_name || makeSignatureSchema(form.full_name).safeParse(form.consent_signature).success
  const canSubmit = parsed.success && sigValid && consentRead && !loading

  async function handleSubmit(e: React.SubmitEvent) {
    e.preventDefault()
    // Mark all fields touched to show any remaining errors
    const allFields = Object.keys(schema.shape) as FormFields[]
    setTouched(Object.fromEntries(allFields.map((f) => [f, true])))
    if (!parsed.success || !sigValid || !consentRead) return

    setError(null)
    setLoading(true)
    try {
      const data = await registerPlayer(parsed.data)
      setIssuedKey(data.api_key)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Registration failed')
    } finally {
      setLoading(false)
    }
  }

  async function copyKey() {
    if (!issuedKey) return
    await navigator.clipboard.writeText(issuedKey)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  function handleConsentScroll(e: React.UIEvent<HTMLDivElement>) {
    if (consentScrolledToBottom) return
    const { scrollTop, clientHeight, scrollHeight } = e.currentTarget
    if (scrollTop + clientHeight >= scrollHeight - 8) {
      setConsentScrolledToBottom(true)
    }
  }

  // Swap to the key-display view once registration succeeds.
  if (issuedKey) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background p-4">
        <div className="fixed top-3 right-3">
          <ThemeToggle />
        </div>
        <Card className="w-full max-w-md">
          <CardHeader>
            <CardTitle>Your Access Key</CardTitle>
            <CardDescription>
              This key will only be shown once. Save it before continuing.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center gap-2">
              <Input readOnly value={issuedKey} className="font-mono text-sm" />
              <Button variant="outline" onClick={copyKey}>
                {copied ? 'Copied!' : 'Copy'}
              </Button>
            </div>
            <Alert>
              <AlertDescription>
                We do not store your key. If you lose it, you will need to register again.
              </AlertDescription>
            </Alert>
            <Button className="w-full" onClick={() => navigate({ to: '/login' })}>
              I have saved my key — Continue to Login
            </Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-background p-4">
      <div className="fixed top-3 right-3">
        <ThemeToggle />
      </div>
      <Card className="w-full max-w-lg">
        <CardHeader>
          <CardTitle>Register</CardTitle>
          <CardDescription>Create an account to receive your access key.</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1">
                <Label htmlFor="full_name">Full Name</Label>
                <Input
                  id="full_name"
                  value={form.full_name}
                  onChange={(e) => set('full_name', e.target.value)}
                  onBlur={() => touch('full_name')}
                />
                <FieldError msg={visibleError('full_name')} />
              </div>
              <div className="space-y-1">
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  type="email"
                  value={form.email}
                  onChange={(e) => set('email', e.target.value)}
                  onBlur={() => touch('email')}
                />
                <FieldError msg={visibleError('email')} />
              </div>
            </div>

            <div className="space-y-1">
              <Label htmlFor="phone_number">Phone Number</Label>
              <Input
                id="phone_number"
                type="tel"
                placeholder="(555) 000-0000"
                value={form.phone_number}
                onChange={(e) => set('phone_number', e.target.value)}
                onBlur={() => touch('phone_number')}
              />
              <FieldError msg={visibleError('phone_number')} />
            </div>

            <div className="space-y-1">
              <Label htmlFor="prior_experience">Prior Experience</Label>
              <Textarea
                id="prior_experience"
                value={form.prior_experience}
                onChange={(e) => set('prior_experience', e.target.value)}
                onBlur={() => touch('prior_experience')}
                rows={3}
              />
              <FieldError msg={visibleError('prior_experience')} />
            </div>

            <div className="space-y-1">
              <Label htmlFor="additional_comments">Additional Comments</Label>
              <Textarea
                id="additional_comments"
                value={form.additional_comments}
                onChange={(e) => set('additional_comments', e.target.value)}
                rows={2}
              />
            </div>

            <div className="flex items-center gap-2">
              <Checkbox
                id="consent_to_followup"
                checked={form.consent_to_followup}
                onCheckedChange={(v) => set('consent_to_followup', Boolean(v))}
              />
              <Label htmlFor="consent_to_followup" className="font-normal">
                I consent to follow-up contact.
              </Label>
            </div>

            <div className="space-y-2">
              <Label htmlFor="consent_text">Consent Form</Label>
              <div
                id="consent_text"
                onScroll={handleConsentScroll}
                className="h-48 overflow-y-auto rounded-md border bg-muted/30 p-3 text-sm leading-6"
              >
                <h4 className="font-semibold">Terms of Use</h4>
                <p className="mt-2">
                  This platform hosts research studies conducted by independent researchers. By
                  accessing or participating in studies on this site, you agree to use the platform
                  in a responsible manner.
                </p>
                <p className="mt-2">
                  <span className="font-medium">Acceptable Use:</span> You may not attempt to
                  interfere with the operation of the platform or any studies hosted on it. This
                  includes attempting to access data that does not belong to you, using automated
                  scripts or bots to complete studies, attempting to reverse engineer study
                  materials, or otherwise disrupting the system.
                </p>
                <p className="mt-2">
                  <span className="font-medium">Independent Researchers:</span> Studies hosted on
                  this platform are created and managed by independent researchers. These
                  researchers are responsible for the design of their studies, obtaining appropriate
                  ethical approval (such as IRB approval), and providing informed consent
                  information to participants.
                </p>
                <p className="mt-2">
                  <span className="font-medium">Research Participation:</span> Participation in any
                  study is voluntary. Each study will provide its own informed consent document
                  describing the purpose of the research, procedures, risks, benefits, and data
                  handling practices.
                </p>
                <p className="mt-2">
                  <span className="font-medium">Platform Availability:</span> The platform is
                  provided for research purposes and may occasionally be unavailable due to
                  maintenance, updates, or technical issues.
                </p>

                <h4 className="mt-4 font-semibold">Privacy Notice</h4>
                <p className="mt-2">
                  This platform hosts research studies conducted by independent researchers.
                  Individual studies may collect research data as described in their informed
                  consent documents.
                </p>
                <p className="mt-2">
                  <span className="font-medium">Platform Data:</span> To operate the platform and
                  support research integrity, the system may collect limited technical information
                  such as timestamps, browser or device information, IP address, and interaction
                  logs related to study participation.
                </p>
                <p className="mt-2">
                  <span className="font-medium">Research Data:</span> Data collected within a study
                  is determined by the researcher conducting that study and will be described in the
                  study&apos;s informed consent document.
                </p>
                <p className="mt-2">
                  <span className="font-medium">Use of Information:</span> Platform data is used to
                  operate the system, troubleshoot technical issues, and help ensure the quality and
                  integrity of research data.
                </p>
                <p className="mt-2">
                  <span className="font-medium">Contact:</span> Questions about a specific study
                  should be directed to the researcher listed in that study&apos;s consent form.
                </p>
              </div>
              {!consentScrolledToBottom && (
                <p className="text-xs text-muted-foreground">
                  Scroll to the bottom of the consent form to enable acknowledgment.
                </p>
              )}
            </div>

            <div
              className={`flex items-center gap-2 transition-opacity ${
                consentScrolledToBottom ? 'opacity-100' : 'opacity-50'
              }`}
            >
              <Checkbox
                id="consent_read"
                checked={consentRead}
                onCheckedChange={(v) => {
                  if (consentScrolledToBottom) {
                    setConsentRead(Boolean(v))
                  }
                }}
                disabled={!consentScrolledToBottom}
              />
              <Label
                htmlFor="consent_read"
                className={`font-normal ${
                  consentScrolledToBottom ? '' : 'cursor-not-allowed text-muted-foreground'
                }`}
              >
                I have read and understood the consent form.
              </Label>
            </div>

            <div className="space-y-1">
              <Label htmlFor="consent_signature">Consent Signature</Label>
              <Input
                id="consent_signature"
                value={form.consent_signature}
                onChange={(e) => set('consent_signature', e.target.value)}
                onBlur={() => touch('consent_signature')}
                placeholder="Type your full name to sign"
              />
              <FieldError msg={visibleError('consent_signature')} />
            </div>

            {error && (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}

            <Button type="submit" className="w-full" disabled={!canSubmit}>
              {loading ? 'Registering…' : 'Register'}
            </Button>

            <p className="text-center text-sm text-muted-foreground">
              Already have a key?{' '}
              <Link to="/login" className="underline underline-offset-4 hover:text-primary">
                Sign in
              </Link>
            </p>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}

export const signupRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/signup',
  component: SignupPage,
})
