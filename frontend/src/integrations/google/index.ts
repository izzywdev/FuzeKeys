/**
 * Google Integration Module
 * 
 * This module exports all Google integration components and services.
 */

export { default as GoogleIntegrationPage } from './frontend/GoogleIntegrationPage';
export { default as GoogleSignupForm } from './frontend/components/GoogleSignupForm';
export { default as googleApiService } from './frontend/services/googleApi';

export type {
  GoogleSignupData,
  GoogleSignupConfig,
  GoogleSignupResult,
  GoogleAccount,
  Identity
} from './frontend/services/googleApi'; 