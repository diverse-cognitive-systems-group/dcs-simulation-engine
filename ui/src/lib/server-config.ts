import { useQuery } from '@tanstack/react-query'
import { resolveApiUrl } from './api-url'

export interface ServerConfig {
  mode: 'standard'
  authentication_required: boolean
  registration_enabled: boolean
  runs_enabled: boolean
  default_run_name: string | null
}

interface ServerConfigPayload {
  mode: 'standard'
  authentication_required: boolean
  registration_enabled: boolean
  experiments_enabled: boolean
  default_experiment_name: string | null
}

let cachedServerConfig: ServerConfig | null = null
let inflightServerConfig: Promise<ServerConfig> | null = null

async function fetchServerConfig(): Promise<ServerConfig> {
  const response = await fetch(resolveApiUrl('/api/server/config'))
  if (!response.ok) {
    throw new Error(`Unable to load server config (HTTP ${response.status})`)
  }
  const payload = (await response.json()) as ServerConfigPayload
  const config: ServerConfig = {
    mode: payload.mode,
    authentication_required: payload.authentication_required,
    registration_enabled: payload.registration_enabled,
    runs_enabled: payload.experiments_enabled,
    default_run_name: payload.default_experiment_name,
  }
  cachedServerConfig = config
  return config
}

export function peekServerConfig(): ServerConfig | null {
  return cachedServerConfig
}

export function getServerConfig(): Promise<ServerConfig> {
  if (cachedServerConfig) {
    return Promise.resolve(cachedServerConfig)
  }
  if (!inflightServerConfig) {
    inflightServerConfig = fetchServerConfig().finally(() => {
      inflightServerConfig = null
    })
  }
  return inflightServerConfig
}

export function useServerConfig() {
  return useQuery({
    queryKey: ['server-config'],
    queryFn: getServerConfig,
    initialData: cachedServerConfig ?? undefined,
    staleTime: 5 * 60_000,
  })
}
