import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import federation from '@originjs/vite-plugin-federation';

export default defineConfig({
  plugins: [
    react(),
    federation({
      name: 'fuzeKeysApp',
      filename: 'remoteEntry.js',
      exposes: {
        './FuzeKeysApp': './src/MfeApp',
      },
      shared: {
        react: { singleton: true, requiredVersion: '^19.0.0' },
        'react-dom': { singleton: true, requiredVersion: '^19.0.0' },
      },
    }),
  ],
  // Shim CRA-style env vars so existing source files don't need changing.
  // VITE_API_URL is passed as a Docker build-arg; falls back to the prod URL.
  define: {
    'process.env.REACT_APP_API_URL': JSON.stringify(
      process.env.VITE_API_URL ?? 'https://api.keys.prod.fuzefront.com'
    ),
  },
  base: '/apps/fuzekeys/',
  server: {
    host: '0.0.0.0',
    port: 3004,
    cors: true,
    strictPort: true,
  },
  build: {
    outDir: 'dist-mfe',
    target: 'esnext',
    minify: false,
    cssCodeSplit: false,
  },
});
