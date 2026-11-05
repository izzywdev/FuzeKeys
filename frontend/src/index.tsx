import React from 'react';
import ReactDOM from 'react-dom/client';
import { initBrowserRum, initBrowserTelemetry } from '@izzywdev/fuzefront-telemetry/browser';
import App from './App';

// Observability (family standard P29/P32-P36). Opt-in per build via env; same-origin
// endpoints only. Must run before the first fetch/XHR so calls carry `traceparent`.
// Nothing here may throw into the app, and no key/secret material is ever attached.
const env = import.meta.env;
const serviceName = 'fuzekeys-frontend';
const release = env.VITE_APP_RELEASE ?? env.MODE;

try {
  if (env.VITE_TELEMETRY_ENABLED === 'true') {
    initBrowserTelemetry({
      serviceName,
      serviceVersion: release,
      ...(env.VITE_OTLP_TRACES_ENDPOINT ? { otlpEndpoint: env.VITE_OTLP_TRACES_ENDPOINT } : {}),
    });
  }
  if (env.VITE_RUM_ENABLED === 'true') {
    initBrowserRum({
      serviceName,
      release,
      ...(env.VITE_RUM_ENDPOINT ? { endpoint: env.VITE_RUM_ENDPOINT } : {}),
    });
  }
} catch {
  // Telemetry is best-effort; a failed init must never block rendering.
}

const root = ReactDOM.createRoot(
  document.getElementById('root') as HTMLElement
);

root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
