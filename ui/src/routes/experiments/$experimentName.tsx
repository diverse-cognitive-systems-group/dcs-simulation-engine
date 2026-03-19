import { useQuery } from '@tanstack/react-query'
import { createRoute, redirect, useNavigate, useParams } from '@tanstack/react-router'
import { useEffect, useMemo, useState } from 'react'
import { HttpError, httpClient } from '@/api/http'
import { FatalErrorOverlay } from '@/components/fatal-error-overlay'
import { ThemeToggle } from '@/components/theme-toggle'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { clearAuth, isAuthenticated, setActiveExperimentName } from '@/lib/auth'
import { getServerConfig } from '@/lib/server-config'
import { cn } from '@/lib/utils'
import { rootRoute } from '../__root'

type ScalarValue = string | boolean
type FieldValue = ScalarValue | string[]
type FormResponseMap = Record<string, Record<string, FieldValue>>

interface ExperimentQuestion {
  key: string
  prompt: string
  answer_type:
    | 'string'
    | 'bool'
    | 'single_choice'
    | 'multi_choice'
    | 'number'
    | 'email'
    | 'phone'
    | null
  options?: Array<string | number> | null
  required?: boolean
}

interface ExperimentFormSchema {
  name: string
  before_or_after: 'before' | 'after'
  questions: ExperimentQuestion[]
}

interface ExperimentAssignmentSummary {
  assignment_id: string
  game_name: string
  character_hid: string
  status: 'assigned' | 'in_progress' | 'completed' | 'interrupted'
}

interface ExperimentProgressResponse {
  total: number
  completed: number
  is_complete: boolean
}

interface ExperimentSetupResponse {
  experiment_name: string
  description: string
  is_open: boolean
  forms: ExperimentFormSchema[]
  progress: ExperimentProgressResponse
  current_assignment: ExperimentAssignmentSummary | null
  pending_post_play: boolean
  assignment_completed: boolean
}

interface ExperimentPlayerResponse {
  assignment: ExperimentAssignmentSummary | null
}

function titleCase(value: string): string {
  return value
    .split('_')
    .join(' ')
    .replace(/\b\w/g, (match) => match.toUpperCase())
}

function emptyResponses(forms: ExperimentFormSchema[]): FormResponseMap {
  const next: FormResponseMap = {}
  for (const form of forms) {
    next[form.name] = {}
    for (const question of form.questions) {
      if (question.answer_type === null) continue
      if (question.answer_type === 'bool') {
        next[form.name][question.key] = false
        continue
      }
      if (question.answer_type === 'multi_choice') {
        next[form.name][question.key] = []
        continue
      }
      next[form.name][question.key] = ''
    }
  }
  return next
}

function validateResponses(
  forms: ExperimentFormSchema[],
  responses: FormResponseMap,
): Record<string, Record<string, string>> {
  const errors: Record<string, Record<string, string>> = {}
  for (const form of forms) {
    const formErrors: Record<string, string> = {}
    const formValues = responses[form.name] ?? {}
    for (const question of form.questions) {
      if (!question.required || question.answer_type === null) continue
      const value = formValues[question.key]
      if (question.answer_type === 'bool') continue
      if (question.answer_type === 'multi_choice') {
        if (!Array.isArray(value) || value.length === 0) {
          formErrors[question.key] = 'Required'
        }
        continue
      }
      if (typeof value !== 'string' || !value.trim()) {
        formErrors[question.key] = 'Required'
      }
    }
    if (Object.keys(formErrors).length > 0) {
      errors[form.name] = formErrors
    }
  }
  return errors
}

function FieldError({ message }: { message?: string }) {
  if (!message || message === 'Required') return null
  return <p className="text-xs text-destructive">{message}</p>
}

function PromptBlock({ prompt }: { prompt: string }) {
  return (
    <div className="rounded-xl border border-border/70 bg-muted/20 px-4 py-4 text-sm leading-6 text-muted-foreground whitespace-pre-wrap">
      {prompt}
    </div>
  )
}

function RequiredHint({ required, invalid }: { required?: boolean; invalid?: boolean }) {
  if (!required) return null
  return (
    <span
      className={cn('text-xs font-normal text-muted-foreground', invalid && 'text-destructive')}
    >
      (required)
    </span>
  )
}

function QuestionPrompt(props: { prompt: string; required?: boolean; invalid?: boolean }) {
  const { prompt, required, invalid } = props
  return (
    <span className="flex flex-wrap items-center gap-1">
      <span>{prompt}</span>
      <RequiredHint required={required} invalid={invalid} />
    </span>
  )
}

function QuestionField(props: {
  formName: string
  question: ExperimentQuestion
  value: FieldValue | undefined
  error?: string
  onChange: (formName: string, key: string, value: FieldValue) => void
}) {
  const { formName, question, value, error, onChange } = props
  const options = (question.options ?? []).map((option) => String(option))
  const invalid = Boolean(error)

  if (question.answer_type === null) {
    return <PromptBlock prompt={question.prompt} />
  }

  if (question.answer_type === 'string') {
    return (
      <div className="space-y-2">
        <Label htmlFor={`${formName}-${question.key}`}>
          <QuestionPrompt prompt={question.prompt} required={question.required} invalid={invalid} />
        </Label>
        <Textarea
          id={`${formName}-${question.key}`}
          value={typeof value === 'string' ? value : ''}
          onChange={(event) => onChange(formName, question.key, event.target.value)}
          rows={4}
          aria-invalid={invalid || undefined}
        />
        <FieldError message={error} />
      </div>
    )
  }

  if (question.answer_type === 'bool') {
    return (
      <div className="space-y-2 rounded-lg border border-border/70 bg-muted/20 px-4 py-3">
        <label htmlFor={`${formName}-${question.key}`} className="flex items-start gap-3 text-sm">
          <Checkbox
            id={`${formName}-${question.key}`}
            checked={Boolean(value)}
            onCheckedChange={(checked) => onChange(formName, question.key, Boolean(checked))}
          />
          <span className="flex-1">
            <QuestionPrompt
              prompt={question.prompt}
              required={question.required}
              invalid={invalid}
            />
          </span>
        </label>
        <FieldError message={error} />
      </div>
    )
  }

  if (question.answer_type === 'multi_choice') {
    const selected = Array.isArray(value) ? value : []
    return (
      <div className="space-y-3">
        <Label>
          <QuestionPrompt prompt={question.prompt} required={question.required} invalid={invalid} />
        </Label>
        <div className="space-y-2 rounded-lg border border-border/70 bg-muted/20 px-4 py-3">
          {options.map((option) => {
            const checked = selected.includes(option)
            const optionId = `${formName}-${question.key}-${option}`
              .replace(/\s+/g, '-')
              .toLowerCase()
            return (
              <div key={option} className="flex items-start gap-3 text-sm">
                <Checkbox
                  id={optionId}
                  checked={checked}
                  onCheckedChange={(nextChecked) => {
                    const next =
                      nextChecked === true
                        ? [...selected, option]
                        : selected.filter((item) => item !== option)
                    onChange(formName, question.key, next)
                  }}
                />
                <Label htmlFor={optionId} className="font-normal">
                  {option}
                </Label>
              </div>
            )
          })}
        </div>
        <FieldError message={error} />
      </div>
    )
  }

  if (question.answer_type === 'single_choice') {
    return (
      <div className="space-y-3">
        <Label>
          <QuestionPrompt prompt={question.prompt} required={question.required} invalid={invalid} />
        </Label>
        <div className="space-y-2 rounded-lg border border-border/70 bg-muted/20 px-4 py-3">
          {options.map((option) => (
            <label key={option} className="flex items-center gap-3 text-sm">
              <input
                type="radio"
                name={`${formName}-${question.key}`}
                value={option}
                checked={value === option}
                onChange={() => onChange(formName, question.key, option)}
                className="h-4 w-4 accent-primary"
              />
              <span>{option}</span>
            </label>
          ))}
        </div>
        <FieldError message={error} />
      </div>
    )
  }

  if (question.answer_type === 'number') {
    return (
      <div className="space-y-2">
        <Label htmlFor={`${formName}-${question.key}`}>
          <QuestionPrompt prompt={question.prompt} required={question.required} invalid={invalid} />
        </Label>
        <Input
          id={`${formName}-${question.key}`}
          type="number"
          value={typeof value === 'string' ? value : ''}
          onChange={(event) => onChange(formName, question.key, event.target.value)}
          aria-invalid={invalid || undefined}
        />
        <FieldError message={error} />
      </div>
    )
  }

  if (question.answer_type === 'email' || question.answer_type === 'phone') {
    return (
      <div className="space-y-2">
        <Label htmlFor={`${formName}-${question.key}`}>
          <QuestionPrompt prompt={question.prompt} required={question.required} invalid={invalid} />
        </Label>
        <Input
          id={`${formName}-${question.key}`}
          type={question.answer_type}
          value={typeof value === 'string' ? value : ''}
          onChange={(event) => onChange(formName, question.key, event.target.value)}
          aria-invalid={invalid || undefined}
        />
        <FieldError message={error} />
      </div>
    )
  }

  return (
    <div className="space-y-2">
      <Label>
        <QuestionPrompt prompt={question.prompt} required={question.required} invalid={invalid} />
      </Label>
      <Select
        value={typeof value === 'string' ? value : ''}
        onValueChange={(next) => onChange(formName, question.key, next ?? '')}
      >
        <SelectTrigger className="w-full">
          <SelectValue placeholder="Select an option" />
        </SelectTrigger>
        <SelectContent>
          {options.map((option) => (
            <SelectItem key={option} value={option}>
              {option}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <FieldError message={error} />
    </div>
  )
}

function FormSection(props: {
  form: ExperimentFormSchema
  responses: FormResponseMap
  errors: Record<string, Record<string, string>>
  onChange: (formName: string, key: string, value: FieldValue) => void
}) {
  const { form, responses, errors, onChange } = props
  return (
    <div className="space-y-5 rounded-2xl border border-border/70 bg-card px-5 py-5">
      <div className="flex items-center justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.22em] text-muted-foreground">Form</p>
          <h3 className="text-lg font-semibold">{titleCase(form.name)}</h3>
        </div>
        <Badge variant="outline">
          {form.before_or_after === 'before' ? 'Before Play' : 'After Play'}
        </Badge>
      </div>
      {form.questions.map((question) => (
        <QuestionField
          key={`${form.name}-${question.key}`}
          formName={form.name}
          question={question}
          value={responses[form.name]?.[question.key]}
          error={errors[form.name]?.[question.key]}
          onChange={onChange}
        />
      ))}
    </div>
  )
}

function ExperimentPage() {
  const { experimentName } = useParams({ from: '/experiments/$experimentName' })
  const navigate = useNavigate()
  const authenticated = isAuthenticated()
  const [entryResponses, setEntryResponses] = useState<FormResponseMap>({})
  const [entryErrors, setEntryErrors] = useState<Record<string, Record<string, string>>>({})
  const [postResponses, setPostResponses] = useState<FormResponseMap>({})
  const [postErrors, setPostErrors] = useState<Record<string, Record<string, string>>>({})
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState<'entry' | 'session' | 'post' | null>(null)

  useEffect(() => {
    setActiveExperimentName(experimentName)
  }, [experimentName])

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['experiment-setup', experimentName, authenticated],
    enabled: authenticated,
    queryFn: () =>
      httpClient<ExperimentSetupResponse>(
        `/api/experiments/${encodeURIComponent(experimentName)}/setup`,
      ),
  })

  const beforeForms = useMemo(
    () => (data?.forms ?? []).filter((form) => form.before_or_after === 'before'),
    [data?.forms],
  )
  const afterForms = useMemo(
    () => (data?.forms ?? []).filter((form) => form.before_or_after === 'after'),
    [data?.forms],
  )

  useEffect(() => {
    if (!beforeForms.length) return
    setEntryResponses((current) =>
      Object.keys(current).length > 0 ? current : emptyResponses(beforeForms),
    )
  }, [beforeForms])

  useEffect(() => {
    if (!afterForms.length) return
    setPostResponses((current) =>
      Object.keys(current).length > 0 ? current : emptyResponses(afterForms),
    )
  }, [afterForms])

  function setResponse(
    setter: React.Dispatch<React.SetStateAction<FormResponseMap>>,
    formName: string,
    key: string,
    value: FieldValue,
  ) {
    setter((current) => ({
      ...current,
      [formName]: {
        ...(current[formName] ?? {}),
        [key]: value,
      },
    }))
  }

  async function handleLogout() {
    clearAuth()
    await navigate({ to: '/login' })
  }

  async function handleEntrySubmit(event: React.FormEvent) {
    event.preventDefault()
    const errors = validateResponses(beforeForms, entryResponses)
    setEntryErrors(errors)
    if (Object.keys(errors).length > 0) return

    setSubmitError(null)
    setSubmitting('entry')
    try {
      await httpClient<ExperimentPlayerResponse>(
        `/api/experiments/${encodeURIComponent(experimentName)}/players`,
        {
          method: 'POST',
          body: JSON.stringify({ responses: entryResponses }),
        },
      )
      await refetch()
    } catch (submitErr) {
      setSubmitError(submitErr instanceof Error ? submitErr.message : 'Registration failed')
    } finally {
      setSubmitting(null)
    }
  }

  async function handleStartSession() {
    setSubmitError(null)
    setSubmitting('session')
    try {
      const response = await httpClient<{ session_id: string }>(
        `/api/experiments/${encodeURIComponent(experimentName)}/sessions`,
        {
          method: 'POST',
          body: JSON.stringify({ source: 'experiment' }),
        },
      )
      await navigate({
        to: '/play/$sessionId',
        params: { sessionId: response.session_id },
        search: {
          gameName: data?.current_assignment?.game_name ?? '',
          experimentName,
        },
      })
    } catch (submitErr) {
      setSubmitError(
        submitErr instanceof Error ? submitErr.message : 'Unable to start the session.',
      )
    } finally {
      setSubmitting(null)
    }
  }

  async function handlePostPlaySubmit(event: React.FormEvent) {
    event.preventDefault()
    const errors = validateResponses(afterForms, postResponses)
    setPostErrors(errors)
    if (Object.keys(errors).length > 0) return

    setSubmitError(null)
    setSubmitting('post')
    try {
      await httpClient(`/api/experiments/${encodeURIComponent(experimentName)}/post-play`, {
        method: 'POST',
        body: JSON.stringify({ responses: postResponses }),
      })
      setPostErrors({})
      setPostResponses(emptyResponses(afterForms))
      await refetch()
    } catch (submitErr) {
      setSubmitError(submitErr instanceof Error ? submitErr.message : 'Unable to submit feedback.')
    } finally {
      setSubmitting(null)
    }
  }

  if (!authenticated) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background p-4">
        <div className="fixed top-3 right-3">
          <ThemeToggle />
        </div>
        <Card className="w-full max-w-md">
          <CardHeader>
            <CardTitle>{titleCase(experimentName)}</CardTitle>
            <CardDescription>
              Sign in with your access key or register before viewing study details.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Button className="w-full" onClick={() => navigate({ to: '/login' })}>
              Sign in with Access Key
            </Button>
            <Button
              variant="outline"
              className="w-full"
              onClick={() => navigate({ to: '/signup' })}
            >
              Register for an Access Key
            </Button>
            <p className="text-sm text-muted-foreground">
              After you sign in, this page will show your assignment flow and any
              experiment-specific intake questions.
            </p>
          </CardContent>
        </Card>
      </div>
    )
  }

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background p-4">
        <Card className="w-full max-w-lg">
          <CardContent className="pt-6">
            <p className="text-sm text-muted-foreground">Loading experiment setup…</p>
          </CardContent>
        </Card>
      </div>
    )
  }

  if (isError || !data) {
    const message =
      error instanceof HttpError
        ? error.message
        : error instanceof Error
          ? error.message
          : 'Unable to load the experiment right now.'
    return (
      <div className="min-h-screen bg-background">
        <FatalErrorOverlay message={message} onReturn={() => navigate({ to: '/login' })} />
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-background px-4 py-10">
      <div className="fixed top-3 right-3 z-10 flex items-center gap-2">
        <Button variant="outline" size="sm" onClick={handleLogout}>
          Logout
        </Button>
        <ThemeToggle />
      </div>
      <div className="mx-auto flex w-full max-w-5xl flex-col gap-6">
        <div className="flex items-start justify-between gap-4">
          <div className="space-y-3">
            <Badge variant="outline">Experiment</Badge>
            <div>
              <h1 className="text-3xl font-semibold tracking-tight">
                {titleCase(data.experiment_name)}
              </h1>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
                {data.description}
              </p>
            </div>
          </div>
        </div>

        <div>
          <Card className="border-border/70 shadow-sm">
            <CardHeader>
              <CardTitle>Study Progress</CardTitle>
              <CardDescription>
                {data.progress.completed} of {data.progress.total} target sessions completed
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="h-3 overflow-hidden rounded-full bg-muted">
                <div
                  className="h-full rounded-full bg-primary transition-all"
                  style={{
                    width: `${Math.min(
                      100,
                      (data.progress.completed / Math.max(data.progress.total, 1)) * 100,
                    )}%`,
                  }}
                />
              </div>
            </CardContent>
          </Card>
        </div>

        <Card className="border-border/70 shadow-sm">
          <CardHeader>
            <CardTitle>
              {data.pending_post_play
                ? 'Post-Play Feedback'
                : data.current_assignment
                  ? 'Your Assignment'
                  : data.assignment_completed
                    ? 'Study Status'
                    : 'Before-Play Questions'}
            </CardTitle>
            <CardDescription>
              {data.pending_post_play
                ? 'Tell us how the interface felt before you leave.'
                : data.current_assignment
                  ? 'This study only allows play through the assigned session below.'
                  : data.assignment_completed
                    ? 'You have completed all assignments currently available to you.'
                    : 'Complete the experiment-specific questions to receive your assignment.'}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            {submitError && (
              <Alert variant="destructive">
                <AlertDescription>{submitError}</AlertDescription>
              </Alert>
            )}

            {!data.pending_post_play &&
              !data.current_assignment &&
              !data.assignment_completed &&
              !data.is_open && (
                <Alert>
                  <AlertDescription>
                    This experiment has already reached its target quota and is not accepting new
                    participants.
                  </AlertDescription>
                </Alert>
              )}

            {!data.pending_post_play &&
              !data.current_assignment &&
              !data.assignment_completed &&
              data.is_open && (
                <form onSubmit={handleEntrySubmit} className="space-y-6">
                  {beforeForms.map((form) => (
                    <FormSection
                      key={form.name}
                      form={form}
                      responses={entryResponses}
                      errors={entryErrors}
                      onChange={(formName, key, value) =>
                        setResponse(setEntryResponses, formName, key, value)
                      }
                    />
                  ))}
                  <Button type="submit" disabled={submitting === 'entry'}>
                    {submitting === 'entry' ? 'Preparing assignment…' : 'Continue to Assignment'}
                  </Button>
                </form>
              )}

            {data.pending_post_play && (
              <form onSubmit={handlePostPlaySubmit} className="space-y-6">
                {afterForms.map((form) => (
                  <FormSection
                    key={form.name}
                    form={form}
                    responses={postResponses}
                    errors={postErrors}
                    onChange={(formName, key, value) =>
                      setResponse(setPostResponses, formName, key, value)
                    }
                  />
                ))}
                <Button type="submit" disabled={submitting === 'post'}>
                  {submitting === 'post' ? 'Submitting…' : 'Submit Feedback'}
                </Button>
              </form>
            )}

            {data.current_assignment && !data.pending_post_play && (
              <div className="space-y-5">
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="rounded-xl border border-border/70 bg-muted/20 px-4 py-4">
                    <div className="text-xs uppercase tracking-[0.2em] text-muted-foreground">
                      Assigned Game
                    </div>
                    <div className="mt-2 text-2xl font-semibold">
                      {data.current_assignment.game_name}
                    </div>
                  </div>
                  <div className="rounded-xl border border-border/70 bg-muted/20 px-4 py-4">
                    <div className="text-xs uppercase tracking-[0.2em] text-muted-foreground">
                      Assigned Character
                    </div>
                    <div className="mt-2 text-2xl font-semibold">
                      {data.current_assignment.character_hid}
                    </div>
                  </div>
                </div>
                <Alert>
                  <AlertDescription>
                    NPC selection is handled by the game defaults for this study. Free character and
                    game selection are disabled while your assignment is active.
                  </AlertDescription>
                </Alert>
                <Button onClick={handleStartSession} disabled={submitting === 'session'}>
                  {submitting === 'session' ? 'Starting session…' : 'Start Assigned Session'}
                </Button>
              </div>
            )}

            {!data.current_assignment && !data.pending_post_play && data.assignment_completed && (
              <div className="space-y-3 rounded-xl border border-border/70 bg-muted/20 px-4 py-6">
                <p className="text-lg font-medium">
                  Thank you. You have completed all available study assignments.
                </p>
                <p className="text-sm text-muted-foreground">
                  There are no further assignments available for your account right now.
                </p>
              </div>
            )}

            {!data.current_assignment &&
              !data.pending_post_play &&
              !data.assignment_completed &&
              !data.is_open && (
                <Alert>
                  <AlertDescription>
                    The experiment quota has been filled, so there are no new assignments available.
                  </AlertDescription>
                </Alert>
              )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

export const experimentRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/experiments/$experimentName',
  beforeLoad: async () => {
    const serverConfig = await getServerConfig()
    if (serverConfig.mode === 'free_play') {
      throw redirect({ to: '/games' })
    }
  },
  component: ExperimentPage,
})
