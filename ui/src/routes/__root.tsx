// Root route: the top of the TanStack Router tree. Every other route is a child of this one.
// The <Outlet /> renders whichever child route is currently active.

import { createRootRoute, Outlet, redirect } from '@tanstack/react-router'
import { isAuthenticated } from '@/lib/auth'
import { getServerConfig } from '@/lib/server-config'

export const rootRoute = createRootRoute({
  component: () => <Outlet />,
})

// Guard used in beforeLoad on protected routes. TanStack Router catches the thrown
// redirect and navigates to /login before the component ever renders.
export async function requireAuth() {
  const serverConfig = await getServerConfig()
  if (serverConfig.authentication_required && !isAuthenticated()) {
    throw redirect({ to: '/login' })
  }
}
