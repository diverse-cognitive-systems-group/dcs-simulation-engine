import { defineConfig } from 'orval'

const openApiTarget = process.env.ORVAL_OPENAPI_TARGET ?? 'http://localhost:8000/openapi.json'

export default defineConfig({
  dcs: {
    input: {
      target: openApiTarget,
    },
    output: {
      target: 'src/api/generated/index.ts',
      schemas: 'src/api/generated/model',
      client: 'react-query',
      httpClient: 'fetch',
      override: {
        mutator: {
          path: 'src/api/http.ts',
          name: 'httpClient',
        },
      },
    },
  },
})
