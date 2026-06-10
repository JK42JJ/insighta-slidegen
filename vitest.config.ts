// Vitest config — resolves the `@/` path alias (mirrors tsconfig baseUrl/paths)
// so tests placed alongside their layer (src/**/*.test.ts) can import sources.
import path from 'node:path';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts', 'tests/**/*.test.ts'],
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
});
