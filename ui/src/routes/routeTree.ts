// Assembles all routes into a single tree that is passed to createRouter in main.tsx.
// Add new routes here after creating them.

import { rootRoute } from './__root'
import { gameSetupRoute } from './games/$gameName'
import { gamesRoute } from './games/index'
import { indexRoute } from './index'
import { loginRoute } from './login'
import { playRoute } from './play/$sessionId'
import { signupRoute } from './signup'

export const routeTree = rootRoute.addChildren([
  indexRoute,
  loginRoute,
  signupRoute,
  gamesRoute,
  gameSetupRoute,
  playRoute,
])
