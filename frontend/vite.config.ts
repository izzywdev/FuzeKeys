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
      // NOTE: `singleton` is a webpack Module Federation option. This plugin
      // neither types it nor reads it at runtime (grep the dist bundle), so it
      // was dead config that only broke `tsc --noEmit`.
      shared: {
        react: { requiredVersion: '^19.0.0' },
        'react-dom': { requiredVersion: '^19.0.0' },
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
    // Without this, @originjs/vite-plugin-federation emits remoteEntry.js at
    // `${assetsDir}/${filename}` (plugin default for assetsDir is "assets")
    // -> serves at /apps/fuzekeys/assets/remoteEntry.js, while
    // registration/manifest.json's
    // integration.remoteEntry advertises /apps/fuzekeys/remoteEntry.js -- a
    // clean 200 on the wrong URL and 404 on the one the host actually
    // requests. `base + assetsDir + filename` must equal the declared entry;
    // assetsDir: '' keeps remoteEntry.js at the root of `base`.
    assetsDir: '',
  },
});
