import { defineConfig } from 'vite';

// Relative base so the build works at https://<user>.github.io/MWX7/ and anywhere else.
export default defineConfig({
  base: './',
  build: { target: 'es2022' },
});
