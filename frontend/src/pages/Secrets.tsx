import React, { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import toast from 'react-hot-toast';
import secretsApi, { Environment } from '../services/secretsApi';

const Secrets: React.FC = () => {
  const [environments, setEnvironments] = useState<Environment[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await secretsApi.listEnvironments();
      setEnvironments(data.items);
    } catch {
      toast.error('Failed to load environments');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    setSaving(true);
    try {
      await secretsApi.createEnvironment(name.trim(), description.trim() || undefined);
      toast.success(`Environment "${name.trim()}" created`);
      setName('');
      setDescription('');
      setShowCreate(false);
      load();
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to create environment');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="px-4 sm:px-0">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Environments</h1>
          <p className="text-sm text-gray-500">
            Grouped secret lists. Each environment keeps a full snapshot history you can roll back to.
          </p>
        </div>
        <button
          onClick={() => setShowCreate((v) => !v)}
          className="inline-flex items-center gap-2 rounded-md bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700"
        >
          + New environment
        </button>
      </div>

      {showCreate && (
        <form
          onSubmit={handleCreate}
          className="mb-6 rounded-lg border border-gray-200 bg-white p-4"
        >
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label className="block text-sm font-medium text-gray-700">Name</label>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Dev"
                className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:ring-primary-500"
                autoFocus
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">Description</label>
              <input
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Development environment variables"
                className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:ring-primary-500"
              />
            </div>
          </div>
          <div className="mt-3 flex gap-2">
            <button
              type="submit"
              disabled={saving}
              className="rounded-md bg-primary-600 px-3 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50"
            >
              {saving ? 'Creating…' : 'Create'}
            </button>
            <button
              type="button"
              onClick={() => setShowCreate(false)}
              className="rounded-md border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
            >
              Cancel
            </button>
          </div>
        </form>
      )}

      {loading ? (
        <p className="text-gray-500">Loading…</p>
      ) : environments.length === 0 ? (
        <div className="rounded-lg border border-dashed border-gray-300 bg-white p-10 text-center">
          <p className="text-gray-600">No environments yet.</p>
          <p className="text-sm text-gray-400">Create one (e.g. Dev or Prod) to start versioning secrets.</p>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {environments.map((env) => (
            <Link
              key={env.id}
              to={`/secrets/${env.id}`}
              className="block rounded-lg border border-gray-200 bg-white p-5 hover:border-primary-400 hover:shadow-sm transition"
            >
              <div className="flex items-center justify-between">
                <h2 className="text-base font-semibold text-gray-900">{env.name}</h2>
                <span className="rounded-full bg-primary-50 px-2.5 py-0.5 text-xs font-medium text-primary-700">
                  v{env.current_snapshot_version}
                </span>
              </div>
              {env.description && (
                <p className="mt-1 text-sm text-gray-500">{env.description}</p>
              )}
              <dl className="mt-4 flex items-center gap-6 text-sm">
                <div>
                  <dt className="text-gray-400">Secrets</dt>
                  <dd className="font-semibold text-gray-800">{env.secret_count}</dd>
                </div>
                <div>
                  <dt className="text-gray-400">Snapshots</dt>
                  <dd className="font-semibold text-gray-800">{env.snapshot_count}</dd>
                </div>
              </dl>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
};

export default Secrets;
