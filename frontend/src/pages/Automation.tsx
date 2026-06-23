import React, { useState, useEffect } from 'react';

interface AutomationJob {
  job_id: string;
  website: string;
  status: string;
  created_at: string;
  completed_at?: string;
  verification_required: boolean;
  error?: string;
}

interface EmailConfig {
  email_address: string;
  imap_server: string;
  imap_port: number;
  provider: string;
}

interface ServiceStatus {
  email_monitoring: boolean;
  captcha_solving: boolean;
  automation_jobs: number;
  pending_tasks: number;
  email_accounts: number;
}

export default function Automation() {
  const [jobs, setJobs] = useState<AutomationJob[]>([]);
  const [emailConfigs, setEmailConfigs] = useState<EmailConfig[]>([]);
  const [serviceStatus, setServiceStatus] = useState<ServiceStatus | null>(null);
  const [loading, setLoading] = useState(false);

  // Form states
  const [newEmailForm, setNewEmailForm] = useState({
    email_address: '',
    password: '',
    provider: 'gmail'
  });

  const [newJobForm, setNewJobForm] = useState({
    website: '',
    identity_id: 1,
    email_account: '',
    signup_data: {
      email: '',
      username: '',
      password: '',
      first_name: '',
      last_name: ''
    }
  });

  // Load data on component mount
  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 10000); // Refresh every 10 seconds
    return () => clearInterval(interval);
  }, []);

  const loadData = async () => {
    try {
      const [jobsRes, configsRes, statusRes] = await Promise.all([
        fetch('/api/v1/background/automation-jobs'),
        fetch('/api/v1/background/email-configs'),
        fetch('/api/v1/background/status')
      ]);

      if (jobsRes.ok) {
        const jobsData = await jobsRes.json();
        setJobs(jobsData.jobs || []);
      }

      if (configsRes.ok) {
        const configsData = await configsRes.json();
        setEmailConfigs(configsData.email_configs || []);
      }

      if (statusRes.ok) {
        const statusData = await statusRes.json();
        setServiceStatus(statusData);
      }
    } catch (error) {
      console.error('Error loading automation data:', error);
    }
  };

  const addEmailConfig = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setLoading(true);

    try {
      const response = await fetch('/api/v1/background/email-config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newEmailForm)
      });

      if (response.ok) {
        setNewEmailForm({ email_address: '', password: '', provider: 'gmail' });
        loadData();
        alert('Email configuration added successfully!');
      } else {
        const error = await response.json();
        alert(`Error: ${error.detail}`);
      }
    } catch (error) {
      alert('Error adding email configuration');
    } finally {
      setLoading(false);
    }
  };

  const createAutomationJob = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setLoading(true);

    try {
      const response = await fetch('/api/v1/background/automation-job', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newJobForm)
      });

      if (response.ok) {
        const result = await response.json();
        setNewJobForm({
          website: '',
          identity_id: 1,
          email_account: '',
          signup_data: {
            email: '',
            username: '',
            password: '',
            first_name: '',
            last_name: ''
          }
        });
        loadData();
        alert(`Automation job created: ${result.job_id}`);
      } else {
        const error = await response.json();
        alert(`Error: ${error.detail}`);
      }
    } catch (error) {
      alert('Error creating automation job');
    } finally {
      setLoading(false);
    }
  };

  const getStatusBadge = (status: string) => {
    const colors: Record<string, string> = {
      pending: 'bg-yellow-500',
      running: 'bg-blue-500',
      completed: 'bg-green-500',
      failed: 'bg-red-500',
      cancelled: 'bg-gray-500',
      awaiting_verification: 'bg-orange-500'
    };

    const colorClass = colors[status] || 'bg-gray-500';
    
    return (
      <span className={`${colorClass} text-white px-2 py-1 rounded text-xs font-medium`}>
        {status.replace('_', ' ').toUpperCase()}
      </span>
    );
  };

  return (
    <div className="container mx-auto p-6">
      <div className="flex justify-between items-center mb-8">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Automation & Background Services</h1>
          <p className="text-gray-600 mt-2">Manage email monitoring, captcha solving, and automated signups</p>
        </div>
      </div>

      {/* Service Status */}
      {serviceStatus && (
        <div className="bg-white rounded-lg shadow-md p-6 mb-6">
          <h2 className="text-xl font-semibold mb-4">Service Status</h2>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            <div className="text-center">
              <div className={`w-4 h-4 rounded-full mx-auto mb-2 ${serviceStatus.email_monitoring ? 'bg-green-500' : 'bg-red-500'}`}></div>
              <p className="text-sm font-medium">Email Monitoring</p>
              <p className="text-xs text-gray-500">{serviceStatus.email_accounts} accounts</p>
            </div>
            <div className="text-center">
              <div className={`w-4 h-4 rounded-full mx-auto mb-2 ${serviceStatus.captcha_solving ? 'bg-green-500' : 'bg-red-500'}`}></div>
              <p className="text-sm font-medium">Captcha Solving</p>
              <p className="text-xs text-gray-500">AI Powered</p>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-blue-600 mb-1">{serviceStatus.automation_jobs}</div>
              <p className="text-sm font-medium">Total Jobs</p>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-orange-600 mb-1">{serviceStatus.pending_tasks}</div>
              <p className="text-sm font-medium">Pending Tasks</p>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-green-600 mb-1">{serviceStatus.email_accounts}</div>
              <p className="text-sm font-medium">Email Accounts</p>
            </div>
          </div>
        </div>
      )}

      <div className="space-y-6">
        {/* Automation Jobs */}
        <div className="bg-white rounded-lg shadow-md p-6">
          <h2 className="text-xl font-semibold mb-4">Automation Jobs</h2>
          <div className="space-y-4">
            {jobs.length === 0 ? (
              <p className="text-gray-500 text-center py-8">No automation jobs yet</p>
            ) : (
              jobs.map((job) => (
                <div key={job.job_id} className="border rounded-lg p-4">
                  <div className="flex justify-between items-start mb-2">
                    <div>
                      <h3 className="font-semibold">{job.website}</h3>
                      <p className="text-sm text-gray-500">Job ID: {job.job_id}</p>
                    </div>
                    {getStatusBadge(job.status)}
                  </div>
                  <div className="grid grid-cols-2 gap-4 text-sm">
                    <div>
                      <span className="text-gray-500">Created:</span> {new Date(job.created_at).toLocaleString()}
                    </div>
                    {job.completed_at && (
                      <div>
                        <span className="text-gray-500">Completed:</span> {new Date(job.completed_at).toLocaleString()}
                      </div>
                    )}
                    <div>
                      <span className="text-gray-500">Verification Required:</span> {job.verification_required ? 'Yes' : 'No'}
                    </div>
                    {job.error && (
                      <div className="col-span-2">
                        <span className="text-gray-500">Error:</span> <span className="text-red-600">{job.error}</span>
                      </div>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Email Configuration */}
        <div className="bg-white rounded-lg shadow-md p-6">
          <h2 className="text-xl font-semibold mb-4">Email Monitoring</h2>
          
          <form onSubmit={addEmailConfig} className="space-y-4 mb-6">
            <h3 className="font-medium">Add Email Account</h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <label htmlFor="email_address" className="block text-sm font-medium text-gray-700">Email Address</label>
                <input
                  id="email_address"
                  type="email"
                  className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500"
                  value={newEmailForm.email_address}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setNewEmailForm({...newEmailForm, email_address: e.target.value})}
                  required
                />
              </div>
              <div>
                <label htmlFor="password" className="block text-sm font-medium text-gray-700">Password / App Password</label>
                <input
                  id="password"
                  type="password"
                  className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500"
                  value={newEmailForm.password}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setNewEmailForm({...newEmailForm, password: e.target.value})}
                  required
                />
              </div>
              <div>
                <label htmlFor="provider" className="block text-sm font-medium text-gray-700">Provider</label>
                <select
                  id="provider"
                  className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500"
                  value={newEmailForm.provider}
                  onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setNewEmailForm({...newEmailForm, provider: e.target.value})}
                >
                  <option value="gmail">Gmail</option>
                  <option value="outlook">Outlook</option>
                  <option value="yahoo">Yahoo</option>
                </select>
              </div>
            </div>
            <button
              type="submit"
              disabled={loading}
              className="px-4 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700 disabled:opacity-50"
            >
              {loading ? 'Adding...' : 'Add Email Account'}
            </button>
          </form>

          <div>
            <h3 className="font-medium mb-3">Configured Email Accounts</h3>
            <div className="space-y-2">
              {emailConfigs.length === 0 ? (
                <p className="text-gray-500 text-center py-4">No email accounts configured</p>
              ) : (
                emailConfigs.map((config, index) => (
                  <div key={index} className="flex justify-between items-center p-3 border rounded">
                    <div>
                      <span className="font-medium">{config.email_address}</span>
                      <span className="text-sm text-gray-500 ml-2">({config.provider})</span>
                    </div>
                    <span className="px-2 py-1 bg-green-100 text-green-800 rounded text-xs font-medium">Monitoring</span>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>

        {/* Create Automation Job */}
        <div className="bg-white rounded-lg shadow-md p-6">
          <h2 className="text-xl font-semibold mb-4">Create Automation Job</h2>
          
          <form onSubmit={createAutomationJob} className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label htmlFor="website" className="block text-sm font-medium text-gray-700">Website</label>
                <input
                  id="website"
                  placeholder="e.g., github, linkedin, twitter"
                  className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500"
                  value={newJobForm.website}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setNewJobForm({...newJobForm, website: e.target.value})}
                  required
                />
              </div>
              <div>
                <label htmlFor="email_account" className="block text-sm font-medium text-gray-700">Email Account for Verification</label>
                <input
                  id="email_account"
                  type="email"
                  className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500"
                  value={newJobForm.email_account}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setNewJobForm({...newJobForm, email_account: e.target.value})}
                  required
                />
              </div>
            </div>
            
            <div className="space-y-4">
              <h3 className="font-semibold">Signup Data</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label htmlFor="signup_email" className="block text-sm font-medium text-gray-700">Email</label>
                  <input
                    id="signup_email"
                    type="email"
                    className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500"
                    value={newJobForm.signup_data.email}
                    onChange={(e: React.ChangeEvent<HTMLInputElement>) => setNewJobForm({
                      ...newJobForm,
                      signup_data: {...newJobForm.signup_data, email: e.target.value}
                    })}
                    required
                  />
                </div>
                <div>
                  <label htmlFor="signup_username" className="block text-sm font-medium text-gray-700">Username</label>
                  <input
                    id="signup_username"
                    className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500"
                    value={newJobForm.signup_data.username}
                    onChange={(e: React.ChangeEvent<HTMLInputElement>) => setNewJobForm({
                      ...newJobForm,
                      signup_data: {...newJobForm.signup_data, username: e.target.value}
                    })}
                    required
                  />
                </div>
                <div>
                  <label htmlFor="signup_password" className="block text-sm font-medium text-gray-700">Password</label>
                  <input
                    id="signup_password"
                    type="password"
                    className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500"
                    value={newJobForm.signup_data.password}
                    onChange={(e: React.ChangeEvent<HTMLInputElement>) => setNewJobForm({
                      ...newJobForm,
                      signup_data: {...newJobForm.signup_data, password: e.target.value}
                    })}
                    required
                  />
                </div>
                <div>
                  <label htmlFor="signup_first_name" className="block text-sm font-medium text-gray-700">First Name</label>
                  <input
                    id="signup_first_name"
                    className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500"
                    value={newJobForm.signup_data.first_name}
                    onChange={(e: React.ChangeEvent<HTMLInputElement>) => setNewJobForm({
                      ...newJobForm,
                      signup_data: {...newJobForm.signup_data, first_name: e.target.value}
                    })}
                  />
                </div>
                <div>
                  <label htmlFor="signup_last_name" className="block text-sm font-medium text-gray-700">Last Name</label>
                  <input
                    id="signup_last_name"
                    className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500"
                    value={newJobForm.signup_data.last_name}
                    onChange={(e: React.ChangeEvent<HTMLInputElement>) => setNewJobForm({
                      ...newJobForm,
                      signup_data: {...newJobForm.signup_data, last_name: e.target.value}
                    })}
                  />
                </div>
              </div>
            </div>
            
            <button
              type="submit"
              disabled={loading}
              className="w-full px-4 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700 disabled:opacity-50"
            >
              {loading ? 'Creating Job...' : 'Create Automation Job'}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
} 