// Registration page at /signup. Collects participant info, validates with Zod,
// and on success shows a one-time access key that the user must copy before continuing.

import { createRoute, Link, redirect, useNavigate } from '@tanstack/react-router'
import { useState } from 'react'
import { z } from 'zod'
import { ThemeToggle } from '@/components/theme-toggle'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  extractDetail,
  NETWORK_UNAVAILABLE,
  REGISTRATION_FAILED,
  SERVER_ERROR,
} from '@/lib/api-errors'
import { resolveApiUrl } from '@/lib/api-url'
import { getServerConfig } from '@/lib/server-config'
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
    res = await fetch(resolveApiUrl('/api/player/registration'), {
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
                <div className="space-y-3">
                  <h3 className="font-semibold">Consent Form</h3>
                  <p>
                    You are invited to participate in a research study. You may not participant if
                    you are under 18-years-old or located outside of the United States. The purpose
                    of this study is to explore how people with diverse perspectives and abilities
                    interact with others, and how we can make it easier for people of different
                    abilities to engage meaningfully with the world.
                  </p>

                  <h4 className="font-semibold">What Participation Involves</h4>

                  <h5 className="font-medium">Gameplay</h5>
                  <p>
                    You will play a game that involves chatting with simulated characters. The goal
                    is to explore how you interpret what others care about, their goals, and what
                    they may be trying to communicate.
                  </p>

                  <h5 className="font-medium">Conversations</h5>
                  <p>
                    You may be asked to take part in one or more conversations with a researcher.
                    These are flexible in format, length, and topics, depending on your needs.
                    Conversations typically last 20–45 minutes and may be audio recorded with your
                    permission. You are free to skip any questions and may withdraw at any time,
                    even after the study.
                  </p>

                  <h4 className="font-semibold">Voluntary Participation</h4>
                  <p>
                    Your participation is completely voluntary. You may withdraw at any time, for
                    any or no reason without a problem. You are not required to answer any questions
                    you do not wish to. You may choose not to consent to audio recording(s) of
                    conversation(s).
                  </p>

                  <h4 className="font-semibold">Privacy and Confidentiality</h4>
                  <p>
                    Contact information will only be collected if you choose to provide it for
                    follow-up purposes; otherwise, responses are anonymous. Audio recordings will
                    only be collected if you verbally consent at the time of the conversation. Any
                    identifiable information will be coded, securely stored, and access limited to
                    protect your identity. The risks of participation are no greater than those of
                    everyday activities. You will not receive financial compensation or direct
                    personal benefits from participation. You may request that your information be
                    deleted at any time.
                  </p>

                  <h4 className="font-semibold">Oversight</h4>
                  <p>
                    This study complies with all applicable laws and confidentiality standards. The
                    Georgia Institute of Technology Institutional Review Board (IRB) and the Office
                    of Human Research Protections may review study records to ensure proper conduct.
                  </p>

                  <h4 className="font-semibold">Contacts</h4>
                  <p>
                    If you have questions about the study, please contact:{' '}
                    <a href="mailto:dcs@psych.gatech.edu" className="underline">
                      dcs@psych.gatech.edu
                    </a>
                  </p>
                  <p>
                    If you have questions about your rights as a research participant, please
                    contact the Georgia Institute of Technology Office of Research Integrity
                    Assurance at{' '}
                    <a href="mailto:IRB@gatech.edu" className="underline">
                      IRB@gatech.edu
                    </a>
                    .
                  </p>

                  <h4 className="font-semibold">Consent</h4>
                  <p>
                    By completing this form, you indicate your consent to participate in the
                    following areas of this study.
                  </p>
                </div>
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
              By registering you agree to our{' '}
              <Link to="/terms" className="underline underline-offset-4 hover:text-primary">
                Terms of Use &amp; Privacy Notice
              </Link>
              .
            </p>

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
  beforeLoad: async () => {
    const serverConfig = await getServerConfig()
    if (!serverConfig.registration_enabled) {
      throw redirect({ to: '/run' })
    }
  },
  component: SignupPage,
})
