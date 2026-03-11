// Login page at /login. Accepts an access key, validates it against the API,
// and on success stores credentials in sessionStorage and navigates to /games.

import { createRoute, Link, useNavigate } from '@tanstack/react-router'
import { useState } from 'react'
import { ThemeToggle } from '@/components/theme-toggle'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { extractDetail, NETWORK_UNAVAILABLE, SIGNIN_UNAVAILABLE } from '@/lib/api-errors'
import { setAuth } from '@/lib/auth'
import { rootRoute } from './__root'

async function authPlayer(apiKey: string): Promise<{ player_id: string; full_name: string }> {
  let res: Response
  try {
    res = await fetch('/api/player/auth', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ api_key: apiKey }),
    })
  } catch {
    throw new Error(NETWORK_UNAVAILABLE)
  }

  if (!res.ok) {
    const detail = await extractDetail(res)

    if (res.status === 401 || res.status === 403) {
      throw new Error('Invalid access key')
    }

    if (res.status >= 500) {
      throw new Error(NETWORK_UNAVAILABLE)
    }

    throw new Error(detail ?? SIGNIN_UNAVAILABLE)
  }
  return res.json()
}

function LoginPage() {
  // useNavigate returns a function for programmatic navigation after form submission.
  const navigate = useNavigate()
  // useState holds form field values and UI state; each call returns [value, setter].
  const [apiKey, setApiKey] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: React.SubmitEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const data = await authPlayer(apiKey.trim())
      setAuth(apiKey.trim(), data.player_id, data.full_name)
      // On success, navigate to the games list.
      await navigate({ to: '/games' })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-background p-4">
      <div className="fixed top-3 right-3">
        <ThemeToggle />
      </div>
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>DCS Simulation</CardTitle>
          <CardDescription>Enter your access key to continue.</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="api-key">Access Key</Label>
              <Input
                id="api-key"
                type="password"
                placeholder="ak-xxxx-xxxx-xxxx"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                required
                autoFocus
              />
            </div>
            {error && (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
            <Button type="submit" className="w-full" disabled={loading || !apiKey.trim()}>
              {loading ? 'Signing in…' : 'Sign in'}
            </Button>
            <p className="text-center text-sm text-muted-foreground">
              No key?{' '}
              <Link to="/signup" className="underline underline-offset-4 hover:text-primary">
                Register here
              </Link>
            </p>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}

export const loginRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/login',
  component: LoginPage,
})
