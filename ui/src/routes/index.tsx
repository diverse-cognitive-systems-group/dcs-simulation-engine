// Index route for "/". Never renders UI — immediately redirects based on server mode.

import { createRoute, redirect } from '@tanstack/react-router'
import { getActiveExperimentName, isAuthenticated } from '@/lib/auth'
import { getServerConfig } from '@/lib/server-config'
import { rootRoute } from './__root'

const DEFAULT_EXPERIMENT = 'usability-ca'

export const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  // beforeLoad runs before the component mounts; throwing a redirect aborts the navigation.
  beforeLoad: async () => {
    const serverConfig = await getServerConfig()
    if (serverConfig.mode === 'free_play') {
      throw redirect({ to: '/games' })
    }

    const experimentName = getActiveExperimentName()
    if (experimentName) {
      throw redirect({
        to: '/experiments/$experimentName',
        params: { experimentName },
      })
    }
    if (isAuthenticated()) {
      throw redirect({ to: '/games' })
    }
    throw redirect({
      to: '/experiments/$experimentName',
      params: { experimentName: DEFAULT_EXPERIMENT },
    })
  },
  component: () => null,
})
