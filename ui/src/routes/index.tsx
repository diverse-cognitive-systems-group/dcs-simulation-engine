// Index route for "/". Never renders UI; it immediately redirects.

import { createRoute, redirect } from '@tanstack/react-router'
import { isAuthenticated } from '@/lib/auth'
import { getServerConfig } from '@/lib/server-config'
import { rootRoute } from './__root'

export const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  // beforeLoad runs before the component mounts; throwing a redirect aborts the navigation.
  beforeLoad: async () => {
    const serverConfig = await getServerConfig()
    if (serverConfig.authentication_required && !isAuthenticated()) {
      throw redirect({ to: '/login' })
    }
    throw redirect({ to: '/run' })
  },
  component: () => null,
})
