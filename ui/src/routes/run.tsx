import { useQuery } from '@tanstack/react-query'
import { createRoute, redirect, useNavigate } from '@tanstack/react-router'
import { useEffect, useState } from 'react'
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
import {
  clearAuth,
  ensureAnonymousAuth,
  isAuthenticated,
  setActiveExperimentName,
} from '@/lib/auth'
import { getServerConfig } from '@/lib/server-config'
import { cn } from '@/lib/utils'
import { rootRoute } from './__root'

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
  trigger: {
    event:
      | 'before_all_assignments'
      | 'before_assignment'
      | 'after_assignment'
      | 'after_all_assignments'
    match: null
  }
  questions: ExperimentQuestion[]
}

interface ExperimentAssignmentSummary {
  assignment_id: string
  game_name: string
  pc_hid: string
  npc_hid: string
  status: 'assigned' | 'in_progress' | 'completed' | 'interrupted'
  active_session_id?: string | null
  has_pending_forms?: boolean
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
  pending_form_groups: PendingFormGroup[]
  progress: ExperimentProgressResponse
  current_assignment: ExperimentAssignmentSummary | null
  assignment_completed: boolean
  next_assignment: NextAssignmentState | null
  allow_choice_if_multiple: boolean
  require_completion: boolean
  eligible_assignment_options: EligibleAssignmentOption[]
  assignments: ExperimentAssignmentSummary[]
  resumable_session_id?: string | null
}

interface PendingFormGroup {
  group_id: string
  trigger: ExperimentFormSchema['trigger']
  forms: ExperimentFormSchema[]
  assignment_id?: string | null
}

interface ExperimentFormSubmitResponse {
  group_id: string
  trigger: ExperimentFormSchema['trigger']
  assignment_id?: string | null
}

function titleCase(value: string): string {
  return value
    .split('_')
    .join(' ')
    .replace(/\b\w/g, (match) => match.toUpperCase())
}

function triggerLabel(trigger: ExperimentFormSchema['trigger']): string {
  if (trigger.event === 'before_all_assignments') return 'Before All Gameplay'
  if (trigger.event === 'before_assignment') return 'Pre-Gameplay'
  if (trigger.event === 'after_assignment') return 'Post-Gameplay'
  return 'After All Gameplay'
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
        <Badge variant="outline">{triggerLabel(form.trigger)}</Badge>
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

function isAssignmentContinuable(status: ExperimentAssignmentSummary['status']) {
  return status !== 'completed'
}

function assignmentActionLabel(_status: ExperimentAssignmentSummary['status']) {
  return 'Continue'
}

function FormOverlay(props: {
  title: string
  description: string
  forms: ExperimentFormSchema[]
  responses: FormResponseMap
  errors: Record<string, Record<string, string>>
  submitError: string | null
  submitting: boolean
  submitLabel: string
  submittingLabel: string
  onSubmit: (event: React.FormEvent) => void
  onChange: (formName: string, key: string, value: FieldValue) => void
}) {
  const {
    title,
    description,
    forms,
    responses,
    errors,
    submitError,
    submitting,
    submitLabel,
    submittingLabel,
    onSubmit,
    onChange,
  } = props
  return (
    <div
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center bg-background/75 px-4 py-6 backdrop-blur-sm"
      role="dialog"
    >
      <div className="max-h-[calc(100vh-3rem)] w-full max-w-3xl overflow-y-auto rounded-lg border border-border bg-background shadow-xl">
        <div className="border-b border-border/70 px-5 py-4">
          <p className="text-xs uppercase tracking-[0.22em] text-muted-foreground">Required Step</p>
          <h2 className="mt-1 text-xl font-semibold">{title}</h2>
          <p className="mt-1 text-sm leading-6 text-muted-foreground">{description}</p>
        </div>
        <form onSubmit={onSubmit} className="space-y-6 px-5 py-5">
          {submitError && (
            <Alert variant="destructive">
              <AlertDescription>{submitError}</AlertDescription>
            </Alert>
          )}
          {forms.map((form) => (
            <FormSection
              key={form.name}
              form={form}
              responses={responses}
              errors={errors}
              onChange={onChange}
            />
          ))}
          <div className="flex justify-end">
            <Button type="submit" disabled={submitting}>
              {submitting ? submittingLabel : submitLabel}
            </Button>
          </div>
        </form>
      </div>
    </div>
  )
}

function AssignmentChooser(props: {
  options: EligibleAssignmentOption[]
  selectedGame: string | null
  selectedPc: string | null
  selectedNpc: string | null
  submitting: boolean
  onGameChange: (value: string | null) => void
  onPcChange: (value: string | null) => void
  onNpcChange: (value: string | null) => void
  onSelect: (gameName: string, pcHid: string, npcHid: string) => void
}) {
  const {
    options,
    selectedGame,
    selectedPc,
    selectedNpc,
    submitting,
    onGameChange,
    onPcChange,
    onNpcChange,
    onSelect,
  } = props
  const gameOptions = [...new Set(options.map((option) => option.game_name))]
  const gameOptionItems = gameOptions
    .map((game) => options.find((option) => option.game_name === game))
    .filter((option): option is EligibleAssignmentOption => Boolean(option))
  const pcOptionItems = options.filter(
    (option, index, allOptions) =>
      option.game_name === selectedGame &&
      allOptions.findIndex(
        (item) => item.game_name === option.game_name && item.pc_hid === option.pc_hid,
      ) === index,
  )
  const npcOptionItems = options.filter(
    (option, index, allOptions) =>
      option.game_name === selectedGame &&
      option.pc_hid === selectedPc &&
      allOptions.findIndex(
        (item) =>
          item.game_name === option.game_name &&
          item.pc_hid === option.pc_hid &&
          item.npc_hid === option.npc_hid,
      ) === index,
  )

  return (
    <div className="rounded-xl border border-border/70 bg-muted/20 px-4 py-5 space-y-4">
      <div>
        <div className="font-medium">Select next gameplay setup</div>
        <p className="mt-1 text-sm text-muted-foreground">
          Choose one available game and character pairing.
        </p>
      </div>
      <div className="grid gap-4 md:grid-cols-3">
        <div className="space-y-1.5">
          <Label className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Game</Label>
          <Select value={selectedGame ?? ''} onValueChange={onGameChange} disabled={submitting}>
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
            onValueChange={onPcChange}
            disabled={!selectedGame || submitting}
          >
            <SelectTrigger>
              <SelectValue
                placeholder={selectedGame ? 'Select a player character…' : 'Select a game first'}
              />
            </SelectTrigger>
            <SelectContent>
              {pcOptionItems.map((option) => (
                <SelectItem key={option.pc_hid} value={option.pc_hid}>
                  <span className="block">
                    <span className="block">{playerCharacterLabel(option)}</span>
                    <OptionDescription>{option.player_character_description}</OptionDescription>
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
            onValueChange={onNpcChange}
            disabled={!selectedGame || !selectedPc || submitting}
          >
            <SelectTrigger>
              <SelectValue
                placeholder={
                  selectedPc ? 'Select a simulator character…' : 'Select a player character first'
                }
              />
            </SelectTrigger>
            <SelectContent>
              {npcOptionItems.map((option) => (
                <SelectItem key={option.npc_hid} value={option.npc_hid}>
                  <span className="block">
                    <span className="block">{option.npc_hid}</span>
                    <OptionDescription>{option.simulator_character_description}</OptionDescription>
                  </span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>
      <Button
        type="button"
        disabled={!selectedGame || !selectedPc || !selectedNpc || submitting}
        onClick={() =>
          selectedGame &&
          selectedPc &&
          selectedNpc &&
          onSelect(selectedGame, selectedPc, selectedNpc)
        }
      >
        {submitting ? 'Selecting…' : 'Select Gameplay Setup'}
      </Button>
    </div>
  )
}

function RunPage() {
  const navigate = useNavigate()
  const authenticated = isAuthenticated()
  const [formResponses, setFormResponses] = useState<FormResponseMap>({})
  const [formErrors, setFormErrors] = useState<Record<string, Record<string, string>>>({})
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState<'form' | 'session' | 'select' | null>(null)
  const [selectedGame, setSelectedGame] = useState<string | null>(null)
  const [selectedPc, setSelectedPc] = useState<string | null>(null)
  const [selectedNpc, setSelectedNpc] = useState<string | null>(null)

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['run-setup', authenticated],
    enabled: authenticated,
    refetchOnMount: 'always',
    queryFn: () => httpClient<ExperimentSetupResponse>('/api/run/setup'),
  })

  useEffect(() => {
    setActiveExperimentName(data?.experiment_name ?? '')
  }, [data?.experiment_name])

  const nextAssignment = data?.next_assignment ?? null
  const pendingFormGroup = data?.pending_form_groups?.[0] ?? null
  const pendingForms = pendingFormGroup?.forms ?? []
  const eligibleOptions =
    nextAssignment?.mode === 'choice'
      ? nextAssignment.options
      : (data?.eligible_assignment_options ?? [])
  const needsSelection = nextAssignment?.mode === 'choice'
  const needsBeforeForms =
    nextAssignment?.mode === 'blocked' && nextAssignment.reason === 'pending_forms'
  const hasPendingAssignmentForms =
    nextAssignment?.mode === 'blocked' && nextAssignment.reason === 'pending_assignment_forms'
  const noAssignmentsAvailable =
    nextAssignment?.mode === 'none' &&
    (nextAssignment.reason === 'unavailable' || nextAssignment.reason === 'quota_closed')

  const lockedAssignment = nextAssignment?.mode === 'locked' ? nextAssignment.assignment : null
  const unfinishedAssignmentCount = (data?.assignments ?? []).filter(
    (assignment) => assignment.status !== 'completed',
  ).length

  useEffect(() => {
    const nextForms = data?.pending_form_groups?.[0]?.forms ?? []
    setFormErrors({})
    setFormResponses(nextForms.length ? emptyResponses(nextForms) : {})
  }, [data?.pending_form_groups])

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

  async function handleFormSubmit(event: React.FormEvent) {
    event.preventDefault()
    if (!pendingFormGroup) return
    const errors = validateResponses(pendingForms, formResponses)
    setFormErrors(errors)
    if (Object.keys(errors).length > 0) return

    setSubmitError(null)
    setSubmitting('form')
    try {
      await httpClient<ExperimentFormSubmitResponse>('/api/run/forms/submit', {
        method: 'POST',
        body: JSON.stringify({ group_id: pendingFormGroup.group_id, responses: formResponses }),
      })
      await refetch()
    } catch (submitErr) {
      setSubmitError(submitErr instanceof Error ? submitErr.message : 'Unable to submit form.')
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
      const response = await httpClient<{ session_id: string }>('/api/run/sessions', {
        method: 'POST',
        body: JSON.stringify({
          source: 'run',
          assignment_id: assignment.assignment_id,
        }),
      })
      await navigate({
        to: '/play/$sessionId',
        params: { sessionId: response.session_id },
        search: {
          gameName: assignment?.game_name ?? '',
          experimentName: data?.experiment_name ?? '',
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

  async function handleSelectAssignment(gameName: string, pcHid: string, npcHid: string) {
    setSubmitError(null)
    setSubmitting('select')
    try {
      await httpClient('/api/run/assignments/select', {
        method: 'POST',
        body: JSON.stringify({ game_name: gameName, pc_hid: pcHid, npc_hid: npcHid }),
      })
      setSelectedGame(null)
      setSelectedPc(null)
      setSelectedNpc(null)
      await refetch()
    } catch (selectErr) {
      setSubmitError(
        selectErr instanceof Error ? selectErr.message : 'Unable to select gameplay session.',
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
            <CardTitle>{titleCase(data?.experiment_name ?? 'Run')}</CardTitle>
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
              After you sign in, this page will show your gameplay session(s) and any intake
              questions.
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

  const showFormOverlay = Boolean(pendingFormGroup)
  const pageDimmed = showFormOverlay
  const assignments = data.assignments ?? []

  return (
    <div className="min-h-screen bg-background px-4 py-10">
      <div className="fixed top-3 right-3 z-10 flex items-center gap-2">
        <Button variant="outline" size="sm" onClick={handleLogout}>
          Logout
        </Button>
        <ThemeToggle />
      </div>
      <div
        aria-hidden={pageDimmed || undefined}
        className={cn(
          'mx-auto flex w-full max-w-5xl flex-col gap-6 transition-opacity',
          pageDimmed && 'pointer-events-none opacity-45',
        )}
      >
        <div className="flex items-start justify-between gap-4">
          <div className="space-y-3">
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
            <div className="flex flex-wrap items-center justify-between gap-2">
              <CardTitle>Gameplay Sessions</CardTitle>
              {unfinishedAssignmentCount > 0 && (
                <Badge variant="secondary">{unfinishedAssignmentCount} unfinished</Badge>
              )}
            </div>
            <CardDescription>Active and completed gameplay sessions.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {submitError && !showFormOverlay && (
              <Alert variant="destructive">
                <AlertDescription>{submitError}</AlertDescription>
              </Alert>
            )}

            {needsSelection && (
              <AssignmentChooser
                options={eligibleOptions}
                selectedGame={selectedGame}
                selectedPc={selectedPc}
                selectedNpc={selectedNpc}
                submitting={submitting === 'select'}
                onGameChange={(value) => {
                  setSelectedGame(value)
                  setSelectedPc(null)
                  setSelectedNpc(null)
                }}
                onPcChange={(value) => {
                  setSelectedPc(value)
                  setSelectedNpc(null)
                }}
                onNpcChange={setSelectedNpc}
                onSelect={handleSelectAssignment}
              />
            )}

            {needsBeforeForms && (
              <Alert>
                <AlertDescription>Complete the required form to unlock gameplay.</AlertDescription>
              </Alert>
            )}

            {hasPendingAssignmentForms && (
              <Alert>
                <AlertDescription>
                  Complete the required feedback form before starting another gameplay session.
                </AlertDescription>
              </Alert>
            )}

            {data.assignment_completed && (
              <Alert>
                <AlertDescription>
                  Thank you. You have completed all available gameplay sessions.
                </AlertDescription>
              </Alert>
            )}

            {noAssignmentsAvailable && (
              <Alert>
                <AlertDescription>
                  No gameplay sessions are currently available. All slots may be filled.
                </AlertDescription>
              </Alert>
            )}

            {!hasPendingAssignmentForms &&
              !data.assignment_completed &&
              !data.is_open &&
              !noAssignmentsAvailable && (
                <Alert>
                  <AlertDescription>
                    The gameplay session quota has been filled, so there are no new ones available.
                  </AlertDescription>
                </Alert>
              )}

            {assignments.length === 0 && !needsSelection ? (
              <div className="rounded-lg border border-dashed border-border/80 bg-muted/20 px-4 py-6 text-sm text-muted-foreground">
                No gameplay sessions have been created yet.
              </div>
            ) : (
              assignments.map((assignment) => (
                <div
                  key={assignment.assignment_id}
                  className="rounded-xl border border-border/70 bg-muted/20 px-4 py-4"
                >
                  <div className="grid gap-4 sm:grid-cols-[1fr_auto] sm:items-center">
                    <div className="min-w-0">
                      <div className="font-medium">{assignment.game_name}</div>
                      <div className="mt-1 text-sm text-muted-foreground">
                        You're playing as {playerCharacterLabel(assignment)} with simulated
                        character {assignment.npc_hid}
                      </div>
                    </div>
                    <div className="flex flex-wrap items-center gap-2 sm:justify-end">
                      <Badge variant={assignment.status === 'completed' ? 'default' : 'secondary'}>
                        {titleCase(assignment.status)}
                      </Badge>
                      {isAssignmentContinuable(assignment.status) && (
                        <Button
                          type="button"
                          size="sm"
                          onClick={() => handleStartSession(assignment)}
                          disabled={submitting === 'session'}
                        >
                          {submitting === 'session'
                            ? 'Opening…'
                            : assignmentActionLabel(assignment.status)}
                        </Button>
                      )}
                    </div>
                  </div>
                </div>
              ))
            )}
          </CardContent>
        </Card>
      </div>
      {pendingFormGroup && (
        <FormOverlay
          title={triggerLabel(pendingFormGroup.trigger)}
          description="Complete the form."
          forms={pendingForms}
          responses={formResponses}
          errors={formErrors}
          submitError={submitError}
          submitting={submitting === 'form'}
          submitLabel="Submit"
          submittingLabel="Submitting…"
          onSubmit={handleFormSubmit}
          onChange={(formName, key, value) => setResponse(setFormResponses, formName, key, value)}
        />
      )}
    </div>
  )
}

export const runRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/run',
  beforeLoad: async () => {
    const serverConfig = await getServerConfig()
    if (serverConfig.authentication_required) {
      if (!isAuthenticated()) {
        throw redirect({ to: '/login' })
      }
      return
    }
    await ensureAnonymousAuth()
  },
  component: RunPage,
})
