import React, { useCallback, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import toast from 'react-hot-toast';
import secretsApi, {
  Environment,
  Secret,
  SecretVersion,
  Snapshot,
} from '../services/secretsApi';

const MASK = '••••••••••••';

const EnvironmentDetail: React.FC = () => {
  const { envId: envIdParam } = useParams<{ envId: string }>();
  const envId = Number(envIdParam);

  const [env, setEnv] = useState<Environment | null>(null);
  const [secrets, setSecrets] = useState<Secret[]>([]);
  const [loading, setLoading] = useState(true);

  // reveal cache for current values shown in the table: secretId -> value
  const [revealed, setRevealed] = useState<Record<number, string>>({});

  // add/edit form
  const [newKey, setNewKey] = useState('');
  const [newValue, setNewValue] = useState('');
  const [adding, setAdding] = useState(false);

  // drawers / modals
  const [historySecret, setHistorySecret] = useState<Secret | null>(null);
  const [showSnapshots, setShowSnapshots] = useState(false);
  const [showExport, setShowExport] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [e, s] = await Promise.all([
        secretsApi.getEnvironment(envId),
        secretsApi.listSecrets(envId),
      ]);
      setEnv(e);
      setSecrets(s.items);
    } catch {
      toast.error('Failed to load environment');
    } finally {
      setLoading(false);
    }
  }, [envId]);

  useEffect(() => {
    if (!Number.isNaN(envId)) load();
  }, [envId, load]);

  const refreshAfterChange = async () => {
    setRevealed({});
    await load();
  };

  const handleReveal = async (secret: Secret) => {
    if (revealed[secret.id] !== undefined) {
      setRevealed((r) => {
        const next = { ...r };
        delete next[secret.id];
        return next;
      });
      return;
    }
    try {
      const res = await secretsApi.revealSecret(envId, secret.id);
      setRevealed((r) => ({ ...r, [secret.id]: res.value }));
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to reveal value');
    }
  };

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newKey.trim() || !newValue) return;
    setAdding(true);
    try {
      await secretsApi.createSecret(envId, newKey.trim(), newValue);
      toast.success(`Added ${newKey.trim()}`);
      setNewKey('');
      setNewValue('');
      refreshAfterChange();
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to add secret');
    } finally {
      setAdding(false);
    }
  };

  const handleDelete = async (secret: Secret) => {
    if (!window.confirm(`Delete ${secret.key}? History is preserved for rollback.`)) return;
    try {
      await secretsApi.deleteSecret(envId, secret.id);
      toast.success(`Deleted ${secret.key}`);
      refreshAfterChange();
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to delete secret');
    }
  };

  if (loading && !env) return <p className="px-4 text-gray-500">Loading…</p>;

  return (
    <div className="px-4 sm:px-0">
      <nav className="mb-1 text-xs text-gray-400">
        <Link to="/secrets" className="hover:text-primary-600">
          Environments
        </Link>{' '}
        / <span className="text-gray-600">{env?.name}</span>
      </nav>
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold text-gray-900">{env?.name}</h1>
          <span className="rounded-full bg-primary-50 px-2.5 py-0.5 text-xs font-medium text-primary-700">
            snapshot v{env?.current_snapshot_version}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowSnapshots(true)}
            className="rounded-md border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
          >
            History
          </button>
          <button
            onClick={() => setShowExport(true)}
            className="rounded-md border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
          >
            Export .env
          </button>
        </div>
      </div>

      {/* add secret */}
      <form onSubmit={handleAdd} className="mb-4 flex flex-wrap items-end gap-2 rounded-lg border border-gray-200 bg-white p-4">
        <div className="flex-1 min-w-[180px]">
          <label className="block text-xs font-medium text-gray-500">Key</label>
          <input
            value={newKey}
            onChange={(e) => setNewKey(e.target.value)}
            placeholder="DATABASE_URL"
            className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:ring-primary-500"
          />
        </div>
        <div className="flex-1 min-w-[180px]">
          <label className="block text-xs font-medium text-gray-500">Value</label>
          <input
            type="password"
            value={newValue}
            onChange={(e) => setNewValue(e.target.value)}
            placeholder="secret value"
            className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:ring-primary-500"
          />
        </div>
        <button
          type="submit"
          disabled={adding}
          className="rounded-md bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50"
        >
          + Add secret
        </button>
      </form>

      {secrets.length === 0 ? (
        <div className="rounded-lg border border-dashed border-gray-300 bg-white p-10 text-center text-gray-500">
          No secrets in this environment yet.
        </div>
      ) : (
        <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
          <table className="min-w-full divide-y divide-gray-200 text-sm">
            <thead className="bg-gray-50 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
              <tr>
                <th className="px-4 py-3">Key</th>
                <th className="px-4 py-3">Value</th>
                <th className="px-4 py-3">Version</th>
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {secrets.map((s) => (
                <tr key={s.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-medium text-gray-900">{s.key}</td>
                  <td className="px-4 py-3">
                    <code className="rounded bg-gray-100 px-2 py-1 text-gray-600 break-all">
                      {revealed[s.id] !== undefined ? revealed[s.id] : MASK}
                    </code>
                  </td>
                  <td className="px-4 py-3">
                    <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600">
                      v{s.current_version}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right whitespace-nowrap">
                    <button
                      onClick={() => handleReveal(s)}
                      className="text-xs font-medium text-gray-600 hover:text-primary-600"
                    >
                      {revealed[s.id] !== undefined ? 'Hide' : 'Reveal'}
                    </button>
                    <button
                      onClick={() => setHistorySecret(s)}
                      className="ml-3 text-xs font-medium text-primary-600 hover:text-primary-700"
                    >
                      History
                    </button>
                    <button
                      onClick={() => handleDelete(s)}
                      className="ml-3 text-xs font-medium text-red-600 hover:text-red-700"
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="mt-3 text-xs text-gray-400">
        Values are masked by default. Revealing a value is recorded in the audit log.
      </p>

      {historySecret && (
        <HistoryDrawer
          envId={envId}
          secret={historySecret}
          onClose={() => setHistorySecret(null)}
          onRolledBack={() => {
            setHistorySecret(null);
            refreshAfterChange();
          }}
        />
      )}
      {showSnapshots && env && (
        <SnapshotsPanel
          envId={envId}
          onClose={() => setShowSnapshots(false)}
          onRolledBack={() => {
            setShowSnapshots(false);
            refreshAfterChange();
          }}
        />
      )}
      {showExport && env && (
        <ExportModal envId={envId} onClose={() => setShowExport(false)} />
      )}
    </div>
  );
};

// --- History drawer -------------------------------------------------------

const HistoryDrawer: React.FC<{
  envId: number;
  secret: Secret;
  onClose: () => void;
  onRolledBack: () => void;
}> = ({ envId, secret, onClose, onRolledBack }) => {
  const [versions, setVersions] = useState<SecretVersion[]>([]);
  const [values, setValues] = useState<Record<number, string>>({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const data = await secretsApi.listVersions(envId, secret.id);
        setVersions(data.items);
      } catch {
        toast.error('Failed to load history');
      } finally {
        setLoading(false);
      }
    })();
  }, [envId, secret.id]);

  const reveal = async (version: number) => {
    try {
      const res = await secretsApi.revealSecret(envId, secret.id, version);
      setValues((v) => ({ ...v, [version]: res.value }));
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to reveal');
    }
  };

  const rollback = async (version: number) => {
    try {
      await secretsApi.rollbackSecret(envId, secret.id, version);
      toast.success(`${secret.key} rolled back to v${version}`);
      onRolledBack();
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Rollback failed');
    }
  };

  return (
    <div className="fixed inset-0 z-40">
      <div className="absolute inset-0 bg-gray-900/40" onClick={onClose} />
      <aside className="absolute inset-y-0 right-0 flex w-full max-w-md flex-col border-l border-gray-200 bg-white shadow-xl">
        <header className="flex items-start justify-between border-b border-gray-200 px-6 py-4">
          <div>
            <p className="text-xs text-gray-400">History</p>
            <h2 className="text-lg font-semibold text-gray-900">{secret.key}</h2>
            <p className="text-sm text-gray-500">Current is v{secret.current_version}</p>
          </div>
          <button onClick={onClose} aria-label="Close" className="text-xl leading-none text-gray-400 hover:text-gray-700">
            ×
          </button>
        </header>
        <div className="flex-1 overflow-y-auto px-6 py-4">
          {loading ? (
            <p className="text-gray-500">Loading…</p>
          ) : (
            <ol className="space-y-5">
              {versions.map((v) => (
                <li key={v.version} className="border-b border-gray-100 pb-4 last:border-0">
                  <div className="flex items-center justify-between">
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                        v.version === secret.current_version
                          ? 'bg-primary-50 text-primary-700'
                          : 'bg-gray-100 text-gray-600'
                      }`}
                    >
                      v{v.version}
                      {v.version === secret.current_version ? ' · current' : ''}
                      {v.is_rollback ? ` · rollback of v${v.rolled_back_from_version}` : ''}
                    </span>
                    <time className="text-xs text-gray-400">
                      {v.created_at ? new Date(v.created_at).toLocaleString() : ''}
                    </time>
                  </div>
                  {v.change_comment && (
                    <p className="mt-1 text-sm text-gray-600">{v.change_comment}</p>
                  )}
                  <code className="mt-2 block break-all rounded bg-gray-100 px-2 py-1 text-xs text-gray-600">
                    {values[v.version] !== undefined ? values[v.version] : MASK}
                  </code>
                  <div className="mt-2 flex items-center gap-4">
                    <button
                      onClick={() => reveal(v.version)}
                      className="text-xs font-medium text-gray-600 hover:text-primary-600"
                    >
                      Reveal value
                    </button>
                    {v.version !== secret.current_version && (
                      <button
                        onClick={() => rollback(v.version)}
                        className="text-xs font-medium text-primary-600 hover:text-primary-700"
                      >
                        Roll back to v{v.version}
                      </button>
                    )}
                  </div>
                </li>
              ))}
            </ol>
          )}
        </div>
        <footer className="border-t border-gray-200 bg-gray-50 px-6 py-4">
          <p className="text-xs text-gray-500">
            Rolling back appends a new current version carrying the old value. Nothing in the
            history is ever deleted.
          </p>
        </footer>
      </aside>
    </div>
  );
};

// --- Snapshots panel ------------------------------------------------------

const SnapshotsPanel: React.FC<{
  envId: number;
  onClose: () => void;
  onRolledBack: () => void;
}> = ({ envId, onClose, onRolledBack }) => {
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const data = await secretsApi.listSnapshots(envId);
        setSnapshots(data.items);
      } catch {
        toast.error('Failed to load snapshots');
      } finally {
        setLoading(false);
      }
    })();
  }, [envId]);

  const rollback = async (snapshotVersion: number) => {
    if (!window.confirm(`Roll the whole environment back to snapshot v${snapshotVersion}?`)) return;
    try {
      await secretsApi.rollbackEnvironment(envId, snapshotVersion);
      toast.success(`Environment rolled back to v${snapshotVersion}`);
      onRolledBack();
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Rollback failed');
    }
  };

  return (
    <div className="fixed inset-0 z-40">
      <div className="absolute inset-0 bg-gray-900/40" onClick={onClose} />
      <aside className="absolute inset-y-0 right-0 flex w-full max-w-md flex-col border-l border-gray-200 bg-white shadow-xl">
        <header className="flex items-start justify-between border-b border-gray-200 px-6 py-4">
          <div>
            <p className="text-xs text-gray-400">Snapshot history</p>
            <h2 className="text-lg font-semibold text-gray-900">Roll back the environment</h2>
          </div>
          <button onClick={onClose} aria-label="Close" className="text-xl leading-none text-gray-400 hover:text-gray-700">
            ×
          </button>
        </header>
        <div className="flex-1 overflow-y-auto px-6 py-4">
          {loading ? (
            <p className="text-gray-500">Loading…</p>
          ) : (
            <ol className="space-y-3">
              {snapshots.map((s, i) => (
                <li
                  key={s.snapshot_version}
                  className="flex items-center justify-between rounded-md border border-gray-100 px-3 py-2"
                >
                  <div>
                    <div className="flex items-center gap-2">
                      <span
                        className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                          i === 0 ? 'bg-primary-50 text-primary-700' : 'bg-gray-100 text-gray-600'
                        }`}
                      >
                        v{s.snapshot_version}
                        {i === 0 ? ' · current' : ''}
                        {s.is_rollback ? ` · rollback of v${s.rolled_back_from_snapshot}` : ''}
                      </span>
                      {s.label && <span className="text-sm text-gray-700">{s.label}</span>}
                    </div>
                    <p className="mt-0.5 text-xs text-gray-400">
                      {s.created_at ? new Date(s.created_at).toLocaleString() : ''}
                    </p>
                  </div>
                  {i !== 0 && (
                    <button
                      onClick={() => rollback(s.snapshot_version)}
                      className="rounded-md border border-primary-600 px-3 py-1.5 text-xs font-medium text-primary-700 hover:bg-primary-50"
                    >
                      Roll back
                    </button>
                  )}
                </li>
              ))}
            </ol>
          )}
        </div>
      </aside>
    </div>
  );
};

// --- Export modal ---------------------------------------------------------

const ExportModal: React.FC<{ envId: number; onClose: () => void }> = ({ envId, onClose }) => {
  const [values, setValues] = useState<Record<string, string> | null>(null);
  const [reveal, setReveal] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const data = await secretsApi.exportEnvironment(envId);
        setValues(data.values);
      } catch (err: any) {
        toast.error(err?.response?.data?.detail || 'Export failed');
      } finally {
        setLoading(false);
      }
    })();
  }, [envId]);

  const dotenv = (mask: boolean) =>
    Object.entries(values || {})
      .map(([k, v]) => `${k}=${mask ? MASK : v}`)
      .join('\n');

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(dotenv(false));
      toast.success('Copied');
    } catch {
      toast.error('Copy failed');
    }
  };

  const download = () => {
    const blob = new Blob([dotenv(false)], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = '.env';
    a.click();
    URL.revokeObjectURL(url);
  };

  const empty = !loading && (!values || Object.keys(values).length === 0);

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-gray-900/40" onClick={onClose} />
      <div className="relative w-full max-w-lg rounded-lg border border-gray-200 bg-white shadow-xl">
        <header className="flex items-start justify-between border-b border-gray-200 px-6 py-4">
          <h2 className="text-lg font-semibold text-gray-900">Export as .env</h2>
          <button onClick={onClose} aria-label="Close" className="text-xl leading-none text-gray-400 hover:text-gray-700">
            ×
          </button>
        </header>
        <div className="px-6 py-4">
          {loading ? (
            <p className="text-gray-500">Loading…</p>
          ) : empty ? (
            <p className="text-gray-500">This environment has no secrets to export.</p>
          ) : (
            <>
              <label className="mb-3 flex items-center gap-2 text-sm text-gray-600">
                <input
                  type="checkbox"
                  checked={reveal}
                  onChange={(e) => setReveal(e.target.checked)}
                  className="rounded border-gray-300 text-primary-600"
                />
                Reveal values (recorded in the audit log)
              </label>
              <pre className="overflow-x-auto rounded-md bg-gray-900 p-4 text-xs text-gray-100">
                <code>{dotenv(!reveal)}</code>
              </pre>
            </>
          )}
        </div>
        {!empty && !loading && (
          <footer className="flex items-center justify-end gap-2 border-t border-gray-200 bg-gray-50 px-6 py-4">
            <button
              onClick={copy}
              className="rounded-md border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
            >
              Copy
            </button>
            <button
              onClick={download}
              className="rounded-md bg-primary-600 px-3 py-2 text-sm font-medium text-white hover:bg-primary-700"
            >
              Download .env
            </button>
          </footer>
        )}
      </div>
    </div>
  );
};

export default EnvironmentDetail;
