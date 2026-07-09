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
        react: { singleton: true, requiredVersion: '^18.0.0' },
        'react-dom': { singleton: true, requiredVersion: '^18.0.0' },
      },
    }),
  ],
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
