import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { isAxiosError } from 'axios';
import toast from 'react-hot-toast';
import apiClient from '../services/apiClient';

/**
 * Identities page -- live against `/api/v1/identities`.
 *
 * List  : GET    /identities/?limit&offset  (summary rows, no PII, + accounts_count)
 * Detail: GET    /identities/{id}           (decrypted; fetched only when opened)
 * Create: POST   /identities/
 * Edit  : PUT    /identities/{id}
 * Delete: DELETE /identities/{id}
 *
 * The list endpoint deliberately carries no PII, so the cards show only the
 * summary fields; the decrypted detail is fetched on demand when an identity is
 * opened or edited. Nothing here logs request/response bodies.
 *
 * A 401 never reaches this component: apiClient's response interceptor clears
 * the token and redirects to /login.
 */

interface IdentitySummary {
  id: number;
  name: string;
  description: string | null;
  created_at: string;
  accounts_count: number;
}

interface IdentityDetail {
  id: number;
  name: string;
  description: string | null;
  first_name: string;
  last_name: string;
  email: string;
  phone: string | null;
  date_of_birth: string | null;
  address_line1: string | null;
  address_line2: string | null;
  city: string | null;
  state: string | null;
  zip_code: string | null;
  country: string | null;
  profession: string | null;
  company: string | null;
  bio: string | null;
  created_at: string;
  updated_at: string | null;
}

interface Page<T> {
  items: T[];
  page: { offset: number; limit: number; total: number; next_offset: number | null };
}

/** Editable fields, all held as strings by the form. */
interface IdentityFormValues {
  name: string;
  description: string;
  first_name: string;
  last_name: string;
  email: string;
  phone: string;
  date_of_birth: string;
  address_line1: string;
  address_line2: string;
  city: string;
  state: string;
  zip_code: string;
  country: string;
  profession: string;
  company: string;
  bio: string;
}

const EMPTY_FORM: IdentityFormValues = {
  name: '',
  description: '',
  first_name: '',
  last_name: '',
  email: '',
  phone: '',
  date_of_birth: '',
  address_line1: '',
  address_line2: '',
  city: '',
  state: '',
  zip_code: '',
  country: '',
  profession: '',
  company: '',
  bio: '',
};

const OPTIONAL_FIELDS: (keyof IdentityFormValues)[] = [
  'description',
  'phone',
  'date_of_birth',
  'address_line1',
  'address_line2',
  'city',
  'state',
  'zip_code',
  'country',
  'profession',
  'company',
  'bio',
];

const PAGE_SIZE = 100;

const toFormValues = (d: IdentityDetail): IdentityFormValues => ({
  name: d.name,
  description: d.description ?? '',
  first_name: d.first_name,
  last_name: d.last_name,
  email: d.email,
  phone: d.phone ?? '',
  date_of_birth: d.date_of_birth ?? '',
  address_line1: d.address_line1 ?? '',
  address_line2: d.address_line2 ?? '',
  city: d.city ?? '',
  state: d.state ?? '',
  zip_code: d.zip_code ?? '',
  country: d.country ?? '',
  profession: d.profession ?? '',
  company: d.company ?? '',
  bio: d.bio ?? '',
});

/**
 * Request body for POST/PUT. The create schema forbids unknown keys and the
 * update handler only touches non-null fields, so:
 *  - create omits empty optional fields entirely;
 *  - update sends '' for an emptied optional field so it can actually be cleared.
 */
const toRequestBody = (values: IdentityFormValues, isUpdate: boolean) => {
  const body: Record<string, string> = {
    name: values.name.trim(),
    first_name: values.first_name.trim(),
    last_name: values.last_name.trim(),
    email: values.email.trim(),
  };
  for (const field of OPTIONAL_FIELDS) {
    const value = values[field].trim();
    if (value || isUpdate) body[field] = value;
  }
  return body;
};

/** Human message for a failed request. Never echoes request bodies. */
const describeError = (err: unknown, fallback: string): string => {
  if (isAxiosError(err)) {
    if (!err.response) return 'Cannot reach the server. Check your connection and try again.';
    const status = err.response.status;
    const detail = err.response.data?.detail;
    if (status === 404) return 'This identity no longer exists. Refresh the list.';
    if (status === 422) {
      return 'Some fields are invalid. Check the required fields and the email address.';
    }
    if (status >= 500) return fallback;
    if (typeof detail === 'string') return detail;
  }
  return fallback;
};

const formatDate = (iso: string): string => new Date(iso).toLocaleDateString();

/* ----------------------------------------------------------------------- */
/* Shared modal shell: dialog semantics, Escape to close, focus on open.    */
/* ----------------------------------------------------------------------- */

const Modal: React.FC<{
  titleId: string;
  onClose: () => void;
  maxWidth?: string;
  children: React.ReactNode;
}> = ({ titleId, onClose, maxWidth = 'max-w-2xl', children }) => {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    ref.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div className="fixed inset-0 bg-gray-600 bg-opacity-50 flex items-center justify-center z-50">
      <div
        ref={ref}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className={`bg-white rounded-lg p-6 w-full ${maxWidth} mx-4 max-h-[90vh] overflow-y-auto focus:outline-none`}
      >
        {children}
      </div>
    </div>
  );
};

/* ----------------------------------------------------------------------- */
/* Create / edit form                                                       */
/* ----------------------------------------------------------------------- */

interface FieldProps {
  id: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
  required?: boolean;
  placeholder?: string;
}

const Field: React.FC<FieldProps> = ({ id, label, value, onChange, type = 'text', required, placeholder }) => (
  <div>
    <label htmlFor={id} className="block text-sm font-medium text-gray-700 mb-1">
      {label}
      {required ? ' *' : ''}
    </label>
    <input
      id={id}
      type={type}
      className="input-field"
      value={value}
      required={required}
      placeholder={placeholder}
      onChange={(e) => onChange(e.target.value)}
    />
  </div>
);

const IdentityFormModal: React.FC<{
  mode: 'create' | 'edit';
  initial: IdentityFormValues;
  saving: boolean;
  error: string | null;
  onSubmit: (values: IdentityFormValues) => void;
  onCancel: () => void;
}> = ({ mode, initial, saving, error, onSubmit, onCancel }) => {
  const [values, setValues] = useState<IdentityFormValues>(initial);
  const set = (key: keyof IdentityFormValues) => (v: string) =>
    setValues((prev) => ({ ...prev, [key]: v }));

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!saving) onSubmit(values);
  };

  const title = mode === 'create' ? 'Create New Identity' : 'Edit Identity';

  return (
    <Modal titleId="identity-form-title" onClose={saving ? () => undefined : onCancel}>
      <h3 id="identity-form-title" className="text-lg font-semibold text-gray-900 mb-4">
        {title}
      </h3>
      <form onSubmit={handleSubmit} noValidate={false}>
        <div className="space-y-4">
          <div className="border-b border-gray-200 pb-4 space-y-4">
            <h4 className="text-md font-medium text-gray-900">Basic Information</h4>
            <Field id="identity-name" label="Identity Name" required value={values.name} onChange={set('name')} placeholder="e.g., Work Identity" />
            <Field id="identity-description" label="Description" value={values.description} onChange={set('description')} placeholder="e.g., For professional accounts" />
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <Field id="identity-first-name" label="First Name" required value={values.first_name} onChange={set('first_name')} />
              <Field id="identity-last-name" label="Last Name" required value={values.last_name} onChange={set('last_name')} />
            </div>
            <Field id="identity-email" label="Email" type="email" required value={values.email} onChange={set('email')} />
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <Field id="identity-phone" label="Phone Number" type="tel" value={values.phone} onChange={set('phone')} />
              <Field id="identity-dob" label="Date of Birth" type="date" value={values.date_of_birth} onChange={set('date_of_birth')} />
            </div>
          </div>

          <div className="border-b border-gray-200 pb-4 space-y-4">
            <h4 className="text-md font-medium text-gray-900">Address Information</h4>
            <Field id="identity-address1" label="Address Line 1" value={values.address_line1} onChange={set('address_line1')} />
            <Field id="identity-address2" label="Address Line 2" value={values.address_line2} onChange={set('address_line2')} />
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <Field id="identity-city" label="City" value={values.city} onChange={set('city')} />
              <Field id="identity-state" label="State/Province" value={values.state} onChange={set('state')} />
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <Field id="identity-zip" label="ZIP/Postal Code" value={values.zip_code} onChange={set('zip_code')} />
              <Field id="identity-country" label="Country" value={values.country} onChange={set('country')} />
            </div>
          </div>

          <div className="space-y-4">
            <h4 className="text-md font-medium text-gray-900">Professional Information</h4>
            <Field id="identity-profession" label="Profession" value={values.profession} onChange={set('profession')} />
            <Field id="identity-company" label="Company" value={values.company} onChange={set('company')} />
            <div>
              <label htmlFor="identity-bio" className="block text-sm font-medium text-gray-700 mb-1">
                Bio
              </label>
              <textarea
                id="identity-bio"
                className="input-field"
                rows={3}
                value={values.bio}
                onChange={(e) => set('bio')(e.target.value)}
              />
            </div>
          </div>
        </div>

        {error && (
          <p role="alert" className="mt-4 text-sm text-red-700">
            {error}
          </p>
        )}

        <div className="flex justify-end space-x-3 mt-6 pt-4 border-t border-gray-200">
          <button
            type="button"
            onClick={onCancel}
            disabled={saving}
            className="px-4 py-2 text-gray-700 bg-gray-200 rounded-lg hover:bg-gray-300 disabled:opacity-50"
          >
            Cancel
          </button>
          <button type="submit" disabled={saving} className="btn-primary disabled:opacity-50">
            {saving ? 'Saving...' : mode === 'create' ? 'Create Identity' : 'Save Changes'}
          </button>
        </div>
      </form>
    </Modal>
  );
};

/* ----------------------------------------------------------------------- */
/* Detail view                                                              */
/* ----------------------------------------------------------------------- */

const DetailRow: React.FC<{ label: string; value: string | null | undefined }> = ({ label, value }) =>
  value ? (
    <div>
      <dt className="block text-sm font-medium text-gray-700">{label}</dt>
      <dd className="text-gray-900 break-words">{value}</dd>
    </div>
  ) : null;

const IdentityDetailModal: React.FC<{
  summary: IdentitySummary;
  detail: IdentityDetail | null;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
  onEdit: () => void;
  onClose: () => void;
}> = ({ summary, detail, loading, error, onRetry, onEdit, onClose }) => {
  const cityLine = detail
    ? [detail.city, detail.state, detail.zip_code].filter(Boolean).join(', ')
    : '';
  return (
    <Modal titleId="identity-detail-title" onClose={onClose}>
      <h3 id="identity-detail-title" className="text-lg font-semibold text-gray-900 mb-4">
        {summary.name}
      </h3>

      {loading && (
        <p role="status" className="text-gray-600">
          Loading identity details...
        </p>
      )}

      {error && (
        <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-4">
          <p className="text-sm text-red-800">{error}</p>
          <button onClick={onRetry} className="mt-2 text-sm font-medium text-red-800 underline">
            Retry
          </button>
        </div>
      )}

      {detail && (
        <div className="space-y-6">
          <section aria-labelledby="detail-basic">
            <h4 id="detail-basic" className="text-md font-medium text-gray-900 mb-3 border-b border-gray-200 pb-2">
              Basic Information
            </h4>
            <dl className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <DetailRow label="Full Name" value={`${detail.first_name} ${detail.last_name}`.trim()} />
              <DetailRow label="Email" value={detail.email} />
              <DetailRow label="Phone" value={detail.phone} />
              <DetailRow
                label="Date of Birth"
                value={detail.date_of_birth ? formatDate(detail.date_of_birth) : null}
              />
              <DetailRow label="Description" value={detail.description} />
            </dl>
          </section>

          {(detail.address_line1 || detail.address_line2 || cityLine || detail.country) && (
            <section aria-labelledby="detail-address">
              <h4 id="detail-address" className="text-md font-medium text-gray-900 mb-3 border-b border-gray-200 pb-2">
                Address
              </h4>
              <div className="space-y-1 text-gray-900">
                {detail.address_line1 && <p>{detail.address_line1}</p>}
                {detail.address_line2 && <p>{detail.address_line2}</p>}
                {cityLine && <p>{cityLine}</p>}
                {detail.country && <p>{detail.country}</p>}
              </div>
            </section>
          )}

          {(detail.profession || detail.company || detail.bio) && (
            <section aria-labelledby="detail-professional">
              <h4 id="detail-professional" className="text-md font-medium text-gray-900 mb-3 border-b border-gray-200 pb-2">
                Professional
              </h4>
              <dl className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <DetailRow label="Profession" value={detail.profession} />
                <DetailRow label="Company" value={detail.company} />
              </dl>
              {detail.bio && (
                <dl className="mt-3">
                  <DetailRow label="Bio" value={detail.bio} />
                </dl>
              )}
            </section>
          )}

          <section aria-labelledby="detail-accounts">
            <h4 id="detail-accounts" className="text-md font-medium text-gray-900 mb-3 border-b border-gray-200 pb-2">
              Account Details
            </h4>
            <dl className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <DetailRow label="Accounts" value={`${summary.accounts_count} accounts`} />
              <DetailRow label="Created" value={formatDate(detail.created_at)} />
            </dl>
          </section>
        </div>
      )}

      <div className="flex justify-end space-x-3 mt-6 pt-4 border-t border-gray-200">
        <button onClick={onClose} className="px-4 py-2 text-gray-700 bg-gray-200 rounded-lg hover:bg-gray-300">
          Close
        </button>
        <button onClick={onEdit} disabled={!detail} className="btn-primary disabled:opacity-50">
          Edit Identity
        </button>
      </div>
    </Modal>
  );
};

/* ----------------------------------------------------------------------- */
/* Delete confirmation                                                      */
/* ----------------------------------------------------------------------- */

const DeleteConfirmModal: React.FC<{
  identity: IdentitySummary;
  deleting: boolean;
  error: string | null;
  onConfirm: () => void;
  onCancel: () => void;
}> = ({ identity, deleting, error, onConfirm, onCancel }) => (
  <Modal titleId="identity-delete-title" onClose={deleting ? () => undefined : onCancel} maxWidth="max-w-md">
    <h3 id="identity-delete-title" className="text-lg font-semibold text-gray-900 mb-2">
      Delete identity?
    </h3>
    <p className="text-sm text-gray-700">
      This permanently deletes <span className="font-medium">{identity.name}</span>
      {identity.accounts_count > 0
        ? ` and its ${identity.accounts_count} linked ${identity.accounts_count === 1 ? 'account' : 'accounts'}`
        : ''}
      . This cannot be undone.
    </p>
    {error && (
      <p role="alert" className="mt-3 text-sm text-red-700">
        {error}
      </p>
    )}
    <div className="flex justify-end space-x-3 mt-6">
      <button
        onClick={onCancel}
        disabled={deleting}
        className="px-4 py-2 text-gray-700 bg-gray-200 rounded-lg hover:bg-gray-300 disabled:opacity-50"
      >
        Cancel
      </button>
      <button
        onClick={onConfirm}
        disabled={deleting}
        className="px-4 py-2 text-white bg-red-600 rounded-lg hover:bg-red-700 disabled:opacity-50"
      >
        {deleting ? 'Deleting...' : 'Delete'}
      </button>
    </div>
  </Modal>
);

/* ----------------------------------------------------------------------- */
/* Page                                                                     */
/* ----------------------------------------------------------------------- */

type FormState = { mode: 'create' } | { mode: 'edit'; id: number; initial: IdentityFormValues };

const Identities: React.FC = () => {
  const navigate = useNavigate();

  const [identities, setIdentities] = useState<IdentitySummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [formState, setFormState] = useState<FormState | null>(null);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const [selected, setSelected] = useState<IdentitySummary | null>(null);
  const [detail, setDetail] = useState<IdentityDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  const [toDelete, setToDelete] = useState<IdentitySummary | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const fetchIdentities = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // Follow the offset envelope until next_offset is null (same pattern as
      // Accounts.tsx) -- the collection never arrives in one response.
      const all: IdentitySummary[] = [];
      let offset: number | null = 0;
      while (offset !== null) {
        const { data }: { data: Page<IdentitySummary> } = await apiClient.get('/identities/', {
          params: { limit: PAGE_SIZE, offset },
        });
        all.push(...data.items);
        offset = data.page.next_offset;
      }
      if (mounted.current) setIdentities(all);
    } catch (err) {
      if (mounted.current) setError(describeError(err, 'We could not load your identities. Please try again.'));
    } finally {
      if (mounted.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchIdentities();
  }, [fetchIdentities]);

  const loadDetail = useCallback(async (id: number): Promise<IdentityDetail | null> => {
    try {
      const { data } = await apiClient.get<IdentityDetail>(`/identities/${id}`);
      return data;
    } catch (err) {
      if (mounted.current) {
        setDetailError(describeError(err, 'We could not load this identity. Please try again.'));
      }
      return null;
    }
  }, []);

  const openDetail = useCallback(
    async (identity: IdentitySummary) => {
      setSelected(identity);
      setDetail(null);
      setDetailError(null);
      setDetailLoading(true);
      const d = await loadDetail(identity.id);
      if (!mounted.current) return;
      setDetail(d);
      setDetailLoading(false);
    },
    [loadDetail]
  );

  const closeDetail = useCallback(() => {
    setSelected(null);
    setDetail(null);
    setDetailError(null);
  }, []);

  const openEditFromDetail = () => {
    if (!detail) return;
    setFormError(null);
    setFormState({ mode: 'edit', id: detail.id, initial: toFormValues(detail) });
    closeDetail();
  };

  const openEditFromCard = async (identity: IdentitySummary) => {
    // The card has no PII, so fetch the decrypted detail before opening the form.
    setDetailError(null);
    const d = await loadDetail(identity.id);
    if (!mounted.current) return;
    if (!d) {
      toast.error('We could not load this identity. Please try again.');
      return;
    }
    setFormError(null);
    setFormState({ mode: 'edit', id: d.id, initial: toFormValues(d) });
  };

  const openCreate = () => {
    setFormError(null);
    setFormState({ mode: 'create' });
  };

  const closeForm = useCallback(() => {
    setFormState(null);
    setFormError(null);
  }, []);

  const handleSubmit = async (values: IdentityFormValues) => {
    if (!formState) return;
    setSaving(true);
    setFormError(null);
    try {
      if (formState.mode === 'create') {
        await apiClient.post('/identities/', toRequestBody(values, false));
        toast.success('Identity created');
      } else {
        await apiClient.put(`/identities/${formState.id}`, toRequestBody(values, true));
        toast.success('Identity updated');
      }
      if (!mounted.current) return;
      closeForm();
      await fetchIdentities();
    } catch (err) {
      if (mounted.current) {
        setFormError(
          describeError(
            err,
            formState.mode === 'create'
              ? 'We could not create the identity. Please try again.'
              : 'We could not save your changes. Please try again.'
          )
        );
      }
    } finally {
      if (mounted.current) setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!toDelete) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      await apiClient.delete(`/identities/${toDelete.id}`);
      if (!mounted.current) return;
      setIdentities((prev) => prev.filter((i) => i.id !== toDelete.id));
      toast.success('Identity deleted');
      setToDelete(null);
    } catch (err) {
      if (mounted.current) {
        setDeleteError(describeError(err, 'We could not delete the identity. Please try again.'));
      }
    } finally {
      if (mounted.current) setDeleting(false);
    }
  };

  const handleAccountCountClick = (identityId: number, identityName: string) => {
    navigate(`/accounts?identity=${identityId}&name=${encodeURIComponent(identityName)}`);
  };

  const renderBody = () => {
    if (loading) {
      return (
        <div role="status" className="card text-center text-gray-600">
          Loading identities...
        </div>
      );
    }

    if (error) {
      return (
        <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-6">
          <h2 className="text-sm font-semibold text-red-900 mb-1">Could not load identities</h2>
          <p className="text-sm text-red-800">{error}</p>
          <button onClick={() => void fetchIdentities()} className="mt-3 btn-secondary">
            Retry
          </button>
        </div>
      );
    }

    if (identities.length === 0) {
      return (
        <div className="card text-center py-12">
          <h2 className="text-lg font-semibold text-gray-900 mb-2">No identities yet</h2>
          <p className="text-gray-600 mb-4">
            Create your first digital identity to start signing up for accounts with it.
          </p>
          <button onClick={openCreate} className="btn-primary">
            + Create your first identity
          </button>
        </div>
      );
    }

    return (
      <ul className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-6">
        {identities.map((identity) => (
          <li key={identity.id} className="card hover:shadow-lg transition-shadow duration-200">
            <div className="flex justify-between items-start mb-4">
              <div className="min-w-0">
                <h3 className="text-lg font-semibold text-gray-900 break-words">{identity.name}</h3>
                {identity.description && (
                  <p className="text-gray-600 text-sm break-words">{identity.description}</p>
                )}
              </div>
              <button
                onClick={() => handleAccountCountClick(identity.id, identity.name)}
                className="bg-green-100 text-green-800 text-xs px-2 py-1 rounded-full hover:bg-green-200 transition-colors cursor-pointer whitespace-nowrap"
                title={`View accounts for ${identity.name}`}
              >
                {identity.accounts_count} {identity.accounts_count === 1 ? 'account' : 'accounts'}
              </button>
            </div>

            <div className="flex justify-between items-center pt-4 border-t border-gray-200">
              <span className="text-xs text-gray-500">Created {formatDate(identity.created_at)}</span>
              <div className="flex items-center space-x-3">
                <button
                  onClick={() => void openDetail(identity)}
                  className="text-primary-600 hover:text-primary-700 text-sm font-medium"
                  aria-label={`View details for ${identity.name}`}
                >
                  View Details
                </button>
                <button
                  onClick={() => void openEditFromCard(identity)}
                  className="text-gray-600 hover:text-gray-900 text-sm font-medium"
                  aria-label={`Edit ${identity.name}`}
                >
                  Edit
                </button>
                <button
                  onClick={() => {
                    setDeleteError(null);
                    setToDelete(identity);
                  }}
                  className="text-red-600 hover:text-red-800 text-sm font-medium"
                  aria-label={`Delete ${identity.name}`}
                >
                  Delete
                </button>
              </div>
            </div>
          </li>
        ))}
      </ul>
    );
  };

  return (
    <div className="px-4 py-6 sm:px-0">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 mb-2">Digital Identities</h1>
          <p className="text-gray-600">Manage your encrypted digital identities for different use cases</p>
        </div>
        <button onClick={openCreate} className="btn-primary">
          + Create Identity
        </button>
      </div>

      {renderBody()}

      {formState && (
        <IdentityFormModal
          mode={formState.mode}
          initial={formState.mode === 'edit' ? formState.initial : EMPTY_FORM}
          saving={saving}
          error={formError}
          onSubmit={(v) => void handleSubmit(v)}
          onCancel={closeForm}
        />
      )}

      {selected && (
        <IdentityDetailModal
          summary={selected}
          detail={detail}
          loading={detailLoading}
          error={detailError}
          onRetry={() => void openDetail(selected)}
          onEdit={openEditFromDetail}
          onClose={closeDetail}
        />
      )}

      {toDelete && (
        <DeleteConfirmModal
          identity={toDelete}
          deleting={deleting}
          error={deleteError}
          onConfirm={() => void handleDelete()}
          onCancel={() => setToDelete(null)}
        />
      )}
    </div>
  );
};

export default Identities;
