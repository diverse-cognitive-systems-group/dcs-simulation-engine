// Application entry point. Mounts the React tree into the #root div in index.html.
// Sets up TanStack Query (for data fetching) and TanStack Router (for client-side routing).

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createRouter, RouterProvider } from '@tanstack/react-router'
import { createRoot } from 'react-dom/client'
import './index.css'
import { initTheme } from './lib/theme'
import { routeTree } from './routes/routeTree'

initTheme()

// QueryClient holds the in-memory cache. staleTime prevents refetching data that was
// fetched less than 30 seconds ago; retry: 1 retries failed requests once before erroring.
const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, staleTime: 30_000 },
  },
})

const router = createRouter({ routeTree })

// This module augmentation gives TanStack Router full type inference for all routes,
// so useNavigate, useParams, etc. are type-checked against the actual route tree.
declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}

// StrictMode is intentionally omitted: it double-invokes effects in development,
// which terminates WebSocket connections before they can complete the auth handshake.
// biome-ignore lint/style/noNonNullAssertion: standard React entry point — root div always exists
createRoot(document.getElementById('root')!).render(
  <QueryClientProvider client={queryClient}>
    <RouterProvider router={router} />
  </QueryClientProvider>,
)
