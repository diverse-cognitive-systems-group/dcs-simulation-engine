// Index route for "/". Never renders UI — immediately redirects based on server mode.

import { createRoute, redirect } from '@tanstack/react-router'
import { getActiveExperimentName, isAuthenticated } from '@/lib/auth'
import { getServerConfig } from '@/lib/server-config'
import { rootRoute } from './__root'

export const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  // beforeLoad runs before the component mounts; throwing a redirect aborts the navigation.
  beforeLoad: async () => {
    const serverConfig = await getServerConfig()
    if (serverConfig.mode === 'free_play') {
      throw redirect({ to: '/games' })
    }

    const defaultExperimentName = serverConfig.default_experiment_name
    const experimentName = getActiveExperimentName()
    if (experimentName) {
      throw redirect({
        to: '/experiments/$experimentName',
        params: { experimentName },
      })
    }
    if (defaultExperimentName) {
      throw redirect({
        to: '/experiments/$experimentName',
        params: { experimentName: defaultExperimentName },
      })
    }
    if (isAuthenticated()) {
      throw redirect({ to: '/games' })
    }
    throw redirect({ to: '/games' })
  },
  component: () => null,
})
