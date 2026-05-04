// Registration page at /signup. Collects participant info, validates with Zod,
// and on success shows a one-time access key that the user must copy before continuing.

import { createRoute, Link, redirect, useNavigate } from '@tanstack/react-router'
import { useState } from 'react'
import { z } from 'zod'
import { ThemeToggle } from '@/components/theme-toggle'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
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
})

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
  })
  // touched tracks which fields the user has interacted with so we only show errors
  // after they've left a field, not on initial load.
  const [touched, setTouched] = useState<Partial<Record<FormFields, boolean>>>({})
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  // issuedKey is set after successful registration; its presence switches the page
  // to the "copy your key" view instead of the form.
  const [issuedKey, setIssuedKey] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  function set(field: FormFields, value: string) {
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

  function visibleError(field: FormFields) {
    return touched[field] ? fieldErrors[field] : undefined
  }

  const canSubmit = parsed.success && !loading

  async function handleSubmit(e: React.SubmitEvent) {
    e.preventDefault()
    // Mark all fields touched to show any remaining errors
    const allFields = Object.keys(schema.shape) as FormFields[]
    setTouched(Object.fromEntries(allFields.map((f) => [f, true])))
    if (!parsed.success) return

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
