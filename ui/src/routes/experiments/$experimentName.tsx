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
  pc_hid: string
  npc_hid: string
  status: 'assigned' | 'in_progress' | 'completed' | 'interrupted'
  active_session_id?: string | null
  needs_post_play?: boolean
  game_description: string
  player_character_name: string
  player_character_description: string
  simulator_character_description: string
  simulator_character_details_visible: boolean
}

interface ExperimentProgressResponse {
  total: number
  completed: number
  is_complete: boolean
}

interface EligibleAssignmentOption {
  game_name: string
  pc_hid: string
  npc_hid: string
  game_description: string
  player_character_name: string
  player_character_description: string
  simulator_character_description: string
  simulator_character_details_visible: boolean
}

interface NextAssignmentState {
  mode: 'locked' | 'choice' | 'blocked' | 'none'
  reason: string
  assignment: ExperimentAssignmentSummary | null
  options: EligibleAssignmentOption[]
}

interface ExperimentSetupResponse {
  experiment_name: string
  description: string
  is_open: boolean
  forms: ExperimentFormSchema[]
  progress: ExperimentProgressResponse
  current_assignment: ExperimentAssignmentSummary | null
  pending_post_play: boolean
  before_play_complete?: boolean
  assignment_completed: boolean
  next_assignment: NextAssignmentState | null
  allow_choice_if_multiple: boolean
  require_completion: boolean
  has_submitted_before_forms: boolean
  eligible_assignment_options: EligibleAssignmentOption[]
  assignments: ExperimentAssignmentSummary[]
  resumable_session_id?: string | null
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

function OptionDescription({ children }: { children: string }) {
  if (!children) return null
  return <span className="block max-w-xl truncate text-xs text-muted-foreground">{children}</span>
}

function playerCharacterLabel(
  item: Pick<ExperimentAssignmentSummary, 'player_character_name' | 'pc_hid'>,
) {
  if (item.player_character_name && item.player_character_name !== item.pc_hid) {
    return `${item.player_character_name} (${item.pc_hid})`
  }
  return item.pc_hid
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
  const [submitting, setSubmitting] = useState<'entry' | 'session' | 'post' | 'select' | null>(null)
  const [selectedGame, setSelectedGame] = useState<string | null>(null)
  const [selectedPc, setSelectedPc] = useState<string | null>(null)
  const [selectedNpc, setSelectedNpc] = useState<string | null>(null)

  useEffect(() => {
    setActiveExperimentName(experimentName)
  }, [experimentName])

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['experiment-setup', experimentName, authenticated],
    enabled: authenticated,
    refetchOnMount: 'always',
    queryFn: () =>
      httpClient<ExperimentSetupResponse>(
        `/api/experiments/${encodeURIComponent(experimentName)}/setup`,
      ),
  })

  const nextAssignment = data?.next_assignment ?? null
  const eligibleOptions =
    nextAssignment?.mode === 'choice'
      ? nextAssignment.options
      : (data?.eligible_assignment_options ?? [])
  const needsSelection = nextAssignment?.mode === 'choice'
  const needsBeforeForms =
    nextAssignment?.mode === 'blocked' && nextAssignment.reason === 'before_forms'
  const noAssignmentsAvailable =
    nextAssignment?.mode === 'none' &&
    (nextAssignment.reason === 'unavailable' || nextAssignment.reason === 'quota_closed')

  const beforeForms = useMemo(
    () => (data?.forms ?? []).filter((form) => form.before_or_after === 'before'),
    [data?.forms],
  )
  const afterForms = useMemo(
    () => (data?.forms ?? []).filter((form) => form.before_or_after === 'after'),
    [data?.forms],
  )
  const lockedAssignment = nextAssignment?.mode === 'locked' ? nextAssignment.assignment : null
  const completedAssignmentCount = (data?.assignments ?? []).filter(
    (assignment) => assignment.status === 'completed',
  ).length
  const assignmentCount = (data?.assignments ?? []).length

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

  async function handleStartSession(
    assignment: ExperimentAssignmentSummary | null = lockedAssignment,
  ) {
    setSubmitError(null)
    if (!assignment) return
    setSubmitting('session')
    try {
      const response = await httpClient<{ session_id: string }>(
        `/api/experiments/${encodeURIComponent(experimentName)}/sessions`,
        {
          method: 'POST',
          body: JSON.stringify({
            source: 'experiment',
            assignment_id: assignment.assignment_id,
          }),
        },
      )
      await navigate({
        to: '/play/$sessionId',
        params: { sessionId: response.session_id },
        search: {
          gameName: assignment?.game_name ?? '',
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

  async function handleSelectAssignment(gameName: string, pcHid: string, npcHid: string) {
    setSubmitError(null)
    setSubmitting('select')
    try {
      await httpClient(
        `/api/experiments/${encodeURIComponent(experimentName)}/assignments/select`,
        {
          method: 'POST',
          body: JSON.stringify({ game_name: gameName, pc_hid: pcHid, npc_hid: npcHid }),
        },
      )
      await refetch()
    } catch (selectErr) {
      setSubmitError(
        selectErr instanceof Error ? selectErr.message : 'Unable to select assignment.',
      )
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

        <Card className="border-border/70 shadow-sm">
          <CardHeader>
            <CardTitle>Progress</CardTitle>
            <CardDescription>
              {completedAssignmentCount} of {assignmentCount} assignments completed
            </CardDescription>
          </CardHeader>
          <CardContent>
            {(() => {
              const total = assignmentCount
              const pct = total > 0 ? Math.round((completedAssignmentCount / total) * 100) : 0
              return (
                <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
                  <div
                    className="h-full rounded-full bg-primary transition-all duration-300"
                    style={{ width: `${pct}%` }}
                  />
                </div>
              )
            })()}
          </CardContent>
        </Card>

        <Card className="border-border/70 shadow-sm">
          <CardHeader>
            <CardTitle>Next Assignment</CardTitle>
            <CardDescription>
              {data.pending_post_play
                ? 'Post-play feedback is required before the next assignment.'
                : lockedAssignment
                  ? 'Continue with the assignment below.'
                  : needsSelection
                    ? 'Select one of the available assignment combinations.'
                    : data.assignment_completed
                      ? 'You have completed all assignments currently available to you.'
                      : noAssignmentsAvailable
                        ? 'No assignments are currently available for your account.'
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
              !lockedAssignment &&
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
              !lockedAssignment &&
              !data.assignment_completed &&
              data.is_open &&
              needsBeforeForms && (
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

            {needsSelection && (
              <div className="space-y-4">
                {(() => {
                  const gameOptions = [...new Set(eligibleOptions.map((o) => o.game_name))]
                  const gameOptionItems = gameOptions
                    .map((game) => eligibleOptions.find((o) => o.game_name === game))
                    .filter((o): o is EligibleAssignmentOption => Boolean(o))
                  const pcOptionItems = eligibleOptions.filter(
                    (option, index, options) =>
                      option.game_name === selectedGame &&
                      options.findIndex(
                        (item) =>
                          item.game_name === option.game_name && item.pc_hid === option.pc_hid,
                      ) === index,
                  )
                  const npcOptionItems = eligibleOptions.filter(
                    (option, index, options) =>
                      option.game_name === selectedGame &&
                      option.pc_hid === selectedPc &&
                      options.findIndex(
                        (item) =>
                          item.game_name === option.game_name &&
                          item.pc_hid === option.pc_hid &&
                          item.npc_hid === option.npc_hid,
                      ) === index,
                  )
                  return (
                    <div className="rounded-xl border border-border/70 bg-muted/20 px-4 py-5 space-y-4">
                      <div className="space-y-1.5">
                        <Label className="text-xs uppercase tracking-[0.2em] text-muted-foreground">
                          Game
                        </Label>
                        <Select
                          value={selectedGame ?? ''}
                          onValueChange={(val) => {
                            setSelectedGame(val)
                            setSelectedPc(null)
                            setSelectedNpc(null)
                          }}
                          disabled={submitting === 'select'}
                        >
                          <SelectTrigger>
                            <SelectValue placeholder="Select a game…" />
                          </SelectTrigger>
                          <SelectContent>
                            {gameOptionItems.map((option) => (
                              <SelectItem key={option.game_name} value={option.game_name}>
                                <span className="block">
                                  <span className="block">{option.game_name}</span>
                                  <OptionDescription>{option.game_description}</OptionDescription>
                                </span>
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="space-y-1.5">
                        <Label className="text-xs uppercase tracking-[0.2em] text-muted-foreground">
                          Player Character
                        </Label>
                        <Select
                          value={selectedPc ?? ''}
                          onValueChange={(val) => {
                            setSelectedPc(val)
                            setSelectedNpc(null)
                          }}
                          disabled={!selectedGame || submitting === 'select'}
                        >
                          <SelectTrigger>
                            <SelectValue
                              placeholder={
                                selectedGame ? 'Select a player character…' : 'Select a game first'
                              }
                            />
                          </SelectTrigger>
                          <SelectContent>
                            {pcOptionItems.map((option) => (
                              <SelectItem key={option.pc_hid} value={option.pc_hid}>
                                <span className="block">
                                  <span className="block">{playerCharacterLabel(option)}</span>
                                  <OptionDescription>
                                    {option.player_character_description}
                                  </OptionDescription>
                                </span>
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="space-y-1.5">
                        <Label className="text-xs uppercase tracking-[0.2em] text-muted-foreground">
                          Simulator Character
                        </Label>
                        <Select
                          value={selectedNpc ?? ''}
                          onValueChange={setSelectedNpc}
                          disabled={!selectedGame || !selectedPc || submitting === 'select'}
                        >
                          <SelectTrigger>
                            <SelectValue
                              placeholder={
                                selectedPc
                                  ? 'Select a simulator character…'
                                  : 'Select a player character first'
                              }
                            />
                          </SelectTrigger>
                          <SelectContent>
                            {npcOptionItems.map((option) => (
                              <SelectItem key={option.npc_hid} value={option.npc_hid}>
                                <span className="block">
                                  <span className="block">{option.npc_hid}</span>
                                  <OptionDescription>
                                    {option.simulator_character_description}
                                  </OptionDescription>
                                </span>
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <Button
                        type="button"
                        disabled={
                          !selectedGame || !selectedPc || !selectedNpc || submitting === 'select'
                        }
                        onClick={() =>
                          selectedGame &&
                          selectedPc &&
                          selectedNpc &&
                          handleSelectAssignment(selectedGame, selectedPc, selectedNpc)
                        }
                      >
                        {submitting === 'select' ? 'Selecting…' : 'Select Assignment'}
                      </Button>
                    </div>
                  )
                })()}
              </div>
            )}

            {noAssignmentsAvailable && (
              <Alert>
                <AlertDescription>
                  No assignments are currently available. All slots may be filled.
                </AlertDescription>
              </Alert>
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

            {lockedAssignment && !data.pending_post_play && (
              <div className="space-y-5">
                <div className="space-y-5 rounded-xl border border-border/70 bg-muted/20 px-4 py-5">
                  <div>
                    <div className="text-xs uppercase tracking-[0.2em] text-muted-foreground">
                      Game
                    </div>
                    <div className="mt-2 flex flex-wrap items-center gap-2">
                      <span className="text-2xl font-semibold">{lockedAssignment.game_name}</span>
                      <Badge variant="secondary">{titleCase(lockedAssignment.status)}</Badge>
                    </div>
                    <p className="mt-1 text-sm leading-6 text-muted-foreground">
                      {lockedAssignment.game_description}
                    </p>
                  </div>
                  <div>
                    <div className="text-xs uppercase tracking-[0.2em] text-muted-foreground">
                      Player Character
                    </div>
                    <div className="mt-2 text-xl font-semibold">
                      {playerCharacterLabel(lockedAssignment)}
                    </div>
                    <p className="mt-1 text-sm leading-6 text-muted-foreground">
                      {lockedAssignment.player_character_description}
                    </p>
                  </div>
                  <div>
                    <div className="text-xs uppercase tracking-[0.2em] text-muted-foreground">
                      Simulator Character
                    </div>
                    <div className="mt-2 text-xl font-semibold">{lockedAssignment.npc_hid}</div>
                    <p className="mt-1 text-sm leading-6 text-muted-foreground">
                      {lockedAssignment.simulator_character_description}
                    </p>
                  </div>
                </div>
                <Button
                  onClick={() => handleStartSession(lockedAssignment)}
                  disabled={submitting === 'session'}
                >
                  {submitting === 'session' ? 'Opening…' : 'Continue'}
                </Button>
              </div>
            )}

            {!lockedAssignment && !data.pending_post_play && data.assignment_completed && (
              <div className="space-y-3 rounded-xl border border-border/70 bg-muted/20 px-4 py-6">
                <p className="text-lg font-medium">
                  Thank you. You have completed all available study assignments.
                </p>
                <p className="text-sm text-muted-foreground">
                  There are no further assignments available for your account right now.
                </p>
              </div>
            )}

            {!lockedAssignment &&
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

        {(data.assignments ?? []).length > 0 && (
          <Card className="border-border/70 shadow-sm">
            <CardHeader>
              <CardTitle>Assignments</CardTitle>
              <CardDescription>Active and completed gameplay assignments.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {(data.assignments ?? []).map((assignment) => (
                <div
                  key={assignment.assignment_id}
                  className="rounded-xl border border-border/70 bg-muted/20 px-4 py-4"
                >
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <div className="font-medium">{assignment.game_name}</div>
                      <div className="mt-1 text-sm text-muted-foreground">
                        {playerCharacterLabel(assignment)} with simulator character{' '}
                        {assignment.npc_hid}
                      </div>
                    </div>
                    <Badge variant={assignment.status === 'completed' ? 'default' : 'secondary'}>
                      {titleCase(assignment.status)}
                    </Badge>
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>
        )}
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
