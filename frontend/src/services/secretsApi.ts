/**
 * Typed client for the secret-versioning API (`/api/v1/secrets`).
 *
 * The router is versioned, so it uses the versioned `apiClient` (whose baseURL
 * already ends in `/api/v1`). Paths here are resource-relative — they never
 * spell the version prefix. List endpoints never return decrypted values; a
 * value is only returned by `revealSecret` / `exportEnvironment`.
 */
import apiClient from './apiClient';

export interface PageInfo {
  offset: number;
  limit: number;
  total: number;
  next_offset: number | null;
}

export interface Page<T> {
  items: T[];
  page: PageInfo;
}

export interface Environment {
  id: number;
  name: string;
  description: string | null;
  current_snapshot_version: number;
  snapshot_count: number;
  secret_count: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface Secret {
  id: number;
  environment_id: number;
  key: string;
  description: string | null;
  current_version: number;
  is_deleted: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export interface SecretVersion {
  version: number;
  change_comment: string | null;
  is_rollback: boolean;
  rolled_back_from_version: number | null;
  created_at: string | null;
  created_by_user_id: number | null;
}

export interface RevealResult {
  secret_id: number;
  version: number;
  value: string;
}

export interface Snapshot {
  snapshot_version: number;
  label: string | null;
  is_rollback: boolean;
  rolled_back_from_snapshot: number | null;
  created_at: string | null;
}

export interface ExportResult {
  environment_id: number;
  snapshot_version: number | null;
  values: Record<string, string>;
}

const base = '/secrets';

export const secretsApi = {
  // environments
  listEnvironments: (offset = 0, limit = 50) =>
    apiClient
      .get<Page<Environment>>(`${base}/environments`, { params: { offset, limit } })
      .then((r) => r.data),
  getEnvironment: (envId: number) =>
    apiClient.get<Environment>(`${base}/environments/${envId}`).then((r) => r.data),
  createEnvironment: (name: string, description?: string) =>
    apiClient
      .post<Environment>(`${base}/environments`, { name, description })
      .then((r) => r.data),
  deleteEnvironment: (envId: number) =>
    apiClient.delete<void>(`${base}/environments/${envId}`).then((r) => r.data),

  // secrets
  listSecrets: (envId: number, offset = 0, limit = 100) =>
    apiClient
      .get<Page<Secret>>(`${base}/environments/${envId}/secrets`, {
        params: { offset, limit },
      })
      .then((r) => r.data),
  createSecret: (
    envId: number,
    key: string,
    value: string,
    description?: string,
    comment?: string,
  ) =>
    apiClient
      .post<Secret>(`${base}/environments/${envId}/secrets`, {
        key,
        value,
        description,
        comment,
      })
      .then((r) => r.data),
  updateSecret: (envId: number, secretId: number, value: string, comment?: string) =>
    apiClient
      .put<Secret>(`${base}/environments/${envId}/secrets/${secretId}`, {
        value,
        comment,
      })
      .then((r) => r.data),
  deleteSecret: (envId: number, secretId: number) =>
    apiClient
      .delete<void>(`${base}/environments/${envId}/secrets/${secretId}`)
      .then((r) => r.data),

  // versions / reveal / rollback
  listVersions: (envId: number, secretId: number, offset = 0, limit = 100) =>
    apiClient
      .get<Page<SecretVersion>>(
        `${base}/environments/${envId}/secrets/${secretId}/versions`,
        { params: { offset, limit } },
      )
      .then((r) => r.data),
  revealSecret: (envId: number, secretId: number, version?: number) =>
    apiClient
      .post<RevealResult>(
        `${base}/environments/${envId}/secrets/${secretId}/reveal`,
        { version },
      )
      .then((r) => r.data),
  rollbackSecret: (envId: number, secretId: number, version: number) =>
    apiClient
      .post<Secret>(
        `${base}/environments/${envId}/secrets/${secretId}/rollback`,
        { version },
      )
      .then((r) => r.data),

  // snapshots / env rollback / export
  listSnapshots: (envId: number, offset = 0, limit = 100) =>
    apiClient
      .get<Page<Snapshot>>(`${base}/environments/${envId}/snapshots`, {
        params: { offset, limit },
      })
      .then((r) => r.data),
  rollbackEnvironment: (envId: number, snapshotVersion: number) =>
    apiClient
      .post<Environment>(`${base}/environments/${envId}/rollback`, {
        snapshot_version: snapshotVersion,
      })
      .then((r) => r.data),
  exportEnvironment: (envId: number, snapshot?: number) =>
    apiClient
      .get<ExportResult>(`${base}/environments/${envId}/export`, {
        params: snapshot ? { snapshot } : {},
      })
      .then((r) => r.data),
};

export default secretsApi;
