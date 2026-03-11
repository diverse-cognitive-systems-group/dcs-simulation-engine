// Index route for "/". Never renders UI — immediately redirects based on auth state.
// Authenticated users go to /games; unauthenticated users go to /login.

import { createRoute, redirect } from '@tanstack/react-router'
import { isAuthenticated } from '@/lib/auth'
import { rootRoute } from './__root'

export const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  // beforeLoad runs before the component mounts; throwing a redirect aborts the navigation.
  beforeLoad: () => {
    throw redirect({ to: isAuthenticated() ? '/games' : '/login' })
  },
  component: () => null,
})
