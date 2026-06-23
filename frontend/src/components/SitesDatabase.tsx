import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Fragment } from 'react';
import { Tab } from '@headlessui/react';
import {
  MagnifyingGlassIcon,
  FunnelIcon,
  ArrowTopRightOnSquareIcon,
  ChartBarIcon,
  ClockIcon,
  ShieldCheckIcon,
  DevicePhoneMobileIcon,
  ChatBubbleLeftRightIcon,
  LockClosedIcon,
  ComputerDesktopIcon,
} from '@heroicons/react/24/outline';

interface Site {
  id: number;
  name: string;
  display_name: string;
  url: string;
  logo_url: string;
  category: string;
  description: string;
  signup_difficulty: string;
  signin_difficulty: string;
  apikey_difficulty: string;
  overall_difficulty: string;
  requires_email_verification: boolean;
  requires_phone_verification: boolean;
  requires_sms_verification: boolean;
  requires_authenticator: boolean;
  has_captcha: boolean;
  captcha_type: string;
  anti_bot_techniques: string[];
  signup_status: string;
  signin_status: string;
  apikey_status: string;
  implementation_progress: number;
  priority: number;
  estimated_hours: number;
  has_official_api: boolean;
  api_documentation_url: string;
  notes: string;
  created_at: string;
}

interface SitesStats {
  total_sites: number;
  categories: Array<{ name: string; count: number }>;
  implementation_progress: {
    signup_completed: number;
    signin_completed: number;
    apikey_completed: number;
    total_completed: number;
  };
  difficulty_distribution: Record<string, number>;
  estimated_total_hours: number;
}

const SitesDatabase: React.FC = () => {
  const [sites, setSites] = useState<Site[]>([]);
  const [stats, setStats] = useState<SitesStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(true);
  const [page, setPage] = useState(0);
  
  // Filters
  const [searchTerm, setSearchTerm] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('');
  const [difficultyFilter, setDifficultyFilter] = useState('');
  const [priorityFilter, setPriorityFilter] = useState('');

  // Infinite scroll
  const observer = useRef<IntersectionObserver>();
  const lastSiteElementRef = useCallback((node: HTMLDivElement) => {
    if (loading) return;
    if (observer.current) observer.current.disconnect();
    observer.current = new IntersectionObserver(entries => {
      if (entries[0].isIntersecting && hasMore && !loadingMore) {
        loadMoreSites();
      }
    });
    if (node) observer.current.observe(node);
  }, [loading, hasMore, loadingMore]);

  // Use environment variable or default to backend port
  const API_BASE = process.env.REACT_APP_API_URL 
    ? `${process.env.REACT_APP_API_URL}/api/v1/sites`
    : 'http://localhost:8002/api/v1/sites';

  const ITEMS_PER_PAGE = 20;

  useEffect(() => {
    fetchSitesData(true); // Reset on filter change
    fetchStats();
  }, [searchTerm, categoryFilter, difficultyFilter, priorityFilter]);

  const fetchSitesData = async (reset = false) => {
    try {
      if (reset) {
        setLoading(true);
        setSites([]);
        setPage(0);
        setHasMore(true);
      } else {
        setLoadingMore(true);
      }

      const currentPage = reset ? 0 : page;
      const params = new URLSearchParams();
      params.append('skip', (currentPage * ITEMS_PER_PAGE).toString());
      params.append('limit', ITEMS_PER_PAGE.toString());
      
      if (searchTerm) params.append('search', searchTerm);
      if (categoryFilter) params.append('category', categoryFilter);
      if (difficultyFilter) params.append('difficulty', difficultyFilter);
      if (priorityFilter) params.append('priority_min', priorityFilter);
      params.append('sort_by', 'priority');
      params.append('sort_order', 'desc');

      const response = await fetch(`${API_BASE}?${params}`);
      if (!response.ok) throw new Error(`Failed to fetch sites: ${response.status} ${response.statusText}`);
      
      const data = await response.json();
      
      if (reset) {
        setSites(data);
      } else {
        setSites(prev => [...prev, ...data]);
      }

      // Check if we have more data
      setHasMore(data.length === ITEMS_PER_PAGE);
      setPage(currentPage + 1);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
      console.error('Error fetching sites:', err);
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  };

  const loadMoreSites = () => {
    if (!loadingMore && hasMore) {
      fetchSitesData(false);
    }
  };

  const fetchStats = async () => {
    try {
      const response = await fetch(`${API_BASE}/stats/overview`);
      if (!response.ok) throw new Error(`Failed to fetch stats: ${response.status} ${response.statusText}`);
      
      const data = await response.json();
      setStats(data);
    } catch (err) {
      console.error('Failed to fetch stats:', err);
    }
  };

  // Debounced search
  useEffect(() => {
    const timeoutId = setTimeout(() => {
      if (searchTerm !== '' || categoryFilter !== '' || difficultyFilter !== '' || priorityFilter !== '') {
        fetchSitesData(true);
      }
    }, 500);
    return () => clearTimeout(timeoutId);
  }, [searchTerm, categoryFilter, difficultyFilter, priorityFilter]);

  const getDifficultyColor = (difficulty: string) => {
    switch (difficulty.toLowerCase()) {
      case 'easy': return 'bg-green-100 text-green-800';
      case 'medium': return 'bg-yellow-100 text-yellow-800';
      case 'hard': return 'bg-red-100 text-red-800';
      case 'extreme': return 'bg-purple-100 text-purple-800';
      default: return 'bg-gray-100 text-gray-800';
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'completed': return 'bg-green-100 text-green-800';
      case 'in_progress': return 'bg-yellow-100 text-yellow-800';
      case 'failed': return 'bg-red-100 text-red-800';
      case 'blocked': return 'bg-red-100 text-red-800';
      default: return 'bg-gray-100 text-gray-800';
    }
  };

  const getPriorityIcon = (priority: number) => {
    if (priority >= 90) return '🔥';
    if (priority >= 80) return '⭐';
    if (priority >= 70) return '📈';
    return '📝';
  };

  const StatCard = ({ title, value, icon, color }: { title: string; value: string | number; icon: React.ReactNode; color: string }) => (
    <div className="bg-white rounded-lg shadow p-6">
      <div className="flex items-center">
        <div className={`flex-shrink-0 p-3 rounded-lg ${color}`}>
          {icon}
        </div>
        <div className="ml-4">
          <p className="text-sm font-medium text-gray-500">{title}</p>
          <p className="text-2xl font-semibold text-gray-900">{value}</p>
        </div>
      </div>
    </div>
  );

  const SitesOverview = () => (
    <div className="space-y-6">
      {/* Stats Cards */}
      {stats && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          <StatCard
            title="Total Sites"
            value={stats.total_sites}
            icon={<ChartBarIcon className="h-6 w-6 text-white" />}
            color="bg-blue-500"
          />
          <StatCard
            title="Implementations Started"
            value={stats.implementation_progress.total_completed}
            icon={<ClockIcon className="h-6 w-6 text-white" />}
            color="bg-green-500"
          />
          <StatCard
            title="Estimated Hours"
            value={stats.estimated_total_hours}
            icon={<ClockIcon className="h-6 w-6 text-white" />}
            color="bg-yellow-500"
          />
          <StatCard
            title="Categories"
            value={stats.categories.length}
            icon={<FunnelIcon className="h-6 w-6 text-white" />}
            color="bg-purple-500"
          />
        </div>
      )}

      {/* Filters */}
      <div className="bg-white rounded-lg shadow p-6">
        <div className="flex items-center mb-4">
          <FunnelIcon className="h-5 w-5 text-gray-400 mr-2" />
          <h3 className="text-lg font-medium text-gray-900">Filters</h3>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Search Sites</label>
            <div className="relative">
              <MagnifyingGlassIcon className="h-5 w-5 text-gray-400 absolute left-3 top-1/2 transform -translate-y-1/2" />
              <input
                type="text"
                placeholder="Search..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="pl-10 w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
              />
            </div>
          </div>
          
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Category</label>
            <select
              value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value)}
              className="w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
            >
              <option value="">All Categories</option>
              {stats?.categories.map((cat) => (
                <option key={cat.name} value={cat.name}>
                  {cat.name} ({cat.count})
                </option>
              ))}
            </select>
          </div>
          
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Difficulty</label>
            <select
              value={difficultyFilter}
              onChange={(e) => setDifficultyFilter(e.target.value)}
              className="w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
            >
              <option value="">All Difficulties</option>
              <option value="easy">Easy</option>
              <option value="medium">Medium</option>
              <option value="hard">Hard</option>
              <option value="extreme">Extreme</option>
            </select>
          </div>
          
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Min Priority</label>
            <select
              value={priorityFilter}
              onChange={(e) => setPriorityFilter(e.target.value)}
              className="w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
            >
              <option value="">All Priorities</option>
              <option value="90">High (90+)</option>
              <option value="80">Medium-High (80+)</option>
              <option value="70">Medium (70+)</option>
              <option value="50">Low-Medium (50+)</option>
            </select>
          </div>
        </div>
      </div>

      {/* Error Display */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <div className="flex">
            <div className="ml-3">
              <h3 className="text-sm font-medium text-red-800">Error loading sites</h3>
              <div className="mt-2 text-sm text-red-700">
                <p>{error}</p>
              </div>
              <div className="mt-4">
                <button
                  onClick={() => fetchSitesData(true)}
                  className="bg-red-100 px-3 py-2 rounded-md text-sm font-medium text-red-800 hover:bg-red-200"
                >
                  Try Again
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Sites Grid */}
      <div className="bg-white rounded-lg shadow">
        <div className="px-6 py-4 border-b border-gray-200">
          <h3 className="text-lg font-medium text-gray-900">
            Sites Database ({sites.length} loaded{hasMore ? ', loading more...' : ''})
          </h3>
        </div>
        
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
            <span className="ml-2 text-gray-600">Loading sites...</span>
          </div>
        ) : sites.length === 0 ? (
          <div className="text-center py-12">
            <p className="text-gray-500">No sites found matching your criteria.</p>
          </div>
        ) : (
          <div className="divide-y divide-gray-200">
            {sites.map((site, index) => {
              const isLast = index === sites.length - 1;
              return (
                <div
                  key={site.id}
                  ref={isLast ? lastSiteElementRef : null}
                  className="p-6 hover:bg-gray-50 transition-colors"
                  data-testid={`site-item-${site.name}`}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center space-x-3">
                        <div className="flex-shrink-0">
                          {site.logo_url ? (
                            <img
                              src={site.logo_url}
                              alt={site.display_name}
                              className="h-10 w-10 rounded-lg object-cover"
                              onError={(e) => {
                                e.currentTarget.style.display = 'none';
                              }}
                            />
                          ) : (
                            <div className="h-10 w-10 rounded-lg bg-gray-200 flex items-center justify-center">
                              <span className="text-gray-500 font-medium">
                                {site.display_name.charAt(0)}
                              </span>
                            </div>
                          )}
                        </div>
                        <div className="flex-1">
                          <div className="flex items-center space-x-2">
                            <h4 className="text-lg font-medium text-gray-900">
                              {site.display_name}
                            </h4>
                            <span className="text-2xl">{getPriorityIcon(site.priority)}</span>
                            <span className="text-sm text-gray-500">Priority: {site.priority}</span>
                          </div>
                          <p className="text-sm text-gray-600 mt-1">{site.description}</p>
                          <div className="flex items-center space-x-4 mt-2">
                            <a
                              href={site.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-blue-600 hover:text-blue-800 text-sm flex items-center"
                            >
                              {site.url}
                              <ArrowTopRightOnSquareIcon className="h-3 w-3 ml-1" />
                            </a>
                            <span className="text-sm text-gray-500">
                              Category: {site.category}
                            </span>
                          </div>
                        </div>
                      </div>
                      
                      {/* Difficulty and Status Badges */}
                      <div className="mt-4 flex flex-wrap gap-2">
                        <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getDifficultyColor(site.signup_difficulty)}`}>
                          Signup: {site.signup_difficulty}
                        </span>
                        <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getDifficultyColor(site.signin_difficulty)}`}>
                          Signin: {site.signin_difficulty}
                        </span>
                        <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getDifficultyColor(site.apikey_difficulty)}`}>
                          API Key: {site.apikey_difficulty}
                        </span>
                        <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getStatusColor(site.signup_status)}`}>
                          Status: {site.signup_status.replace('_', ' ')}
                        </span>
                      </div>

                      {/* Requirements Icons */}
                      <div className="mt-3 flex items-center space-x-4 text-sm text-gray-500">
                        {site.requires_email_verification && (
                          <div className="flex items-center">
                            <ChatBubbleLeftRightIcon className="h-4 w-4 mr-1" />
                            Email
                          </div>
                        )}
                        {site.requires_phone_verification && (
                          <div className="flex items-center">
                            <DevicePhoneMobileIcon className="h-4 w-4 mr-1" />
                            Phone
                          </div>
                        )}
                        {site.requires_authenticator && (
                          <div className="flex items-center">
                            <ShieldCheckIcon className="h-4 w-4 mr-1" />
                            2FA
                          </div>
                        )}
                        {site.has_captcha && (
                          <div className="flex items-center">
                            <LockClosedIcon className="h-4 w-4 mr-1" />
                            CAPTCHA
                          </div>
                        )}
                        {site.has_official_api && (
                          <div className="flex items-center">
                            <ComputerDesktopIcon className="h-4 w-4 mr-1" />
                            API
                          </div>
                        )}
                        {site.estimated_hours && (
                          <div className="flex items-center">
                            <ClockIcon className="h-4 w-4 mr-1" />
                            {site.estimated_hours}h
                          </div>
                        )}
                      </div>

                      {/* Anti-Bot Techniques - Show for hard/extreme difficulties */}
                      {(site.signup_difficulty === 'hard' || site.signup_difficulty === 'extreme' || 
                        site.signin_difficulty === 'hard' || site.signin_difficulty === 'extreme') && 
                        site.anti_bot_techniques && site.anti_bot_techniques.length > 0 && (
                        <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-lg">
                          <div className="flex items-start">
                            <div className="flex-shrink-0">
                              <ShieldCheckIcon className="h-5 w-5 text-red-500" />
                            </div>
                            <div className="ml-3">
                              <h5 className="text-sm font-medium text-red-800">Anti-Bot Protection</h5>
                              <div className="mt-1 text-sm text-red-700">
                                <p className="mb-2">This site uses advanced techniques to block automation:</p>
                                <ul className="list-disc list-inside space-y-1">
                                  {site.anti_bot_techniques.map((technique, index) => (
                                                                         <li key={index}>
                                       <span className="font-medium">{technique}</span>
                                       {(() => {
                                         const descriptions: Record<string, string> = {
                                           'fingerprinting': ' - Analyzes device/browser characteristics to detect automation',
                                           'behavioral_analysis': ' - Monitors mouse movements and typing patterns',
                                           'rate_limiting': ' - Limits requests per IP/timeframe to prevent automated access',
                                           'hidden_fields': ' - Uses invisible form fields that only bots would fill',
                                           'javascript_challenges': ' - Requires complex JavaScript execution to prove human interaction',
                                           'canvas_fingerprinting': ' - Uses HTML5 canvas to create unique device signatures',
                                           'timing_analysis': ' - Analyzes request timing patterns to detect bots',
                                           'user_agent_detection': ' - Blocks known automation user agents',
                                           'ip_reputation': ' - Blocks IPs associated with bot traffic or VPNs',
                                           'session_validation': ' - Requires persistent session state across requests',
                                           'cookie_validation': ' - Validates complex cookie patterns and persistence',
                                           'csrf_tokens': ' - Uses dynamic tokens that change frequently',
                                           'dynamic_selectors': ' - Changes CSS selectors and DOM structure regularly',
                                           'obfuscated_javascript': ' - Uses encoded/minified JS that\'s hard to reverse engineer'
                                         };
                                         return descriptions[technique] || ' - Advanced bot detection technique';
                                       })()}
                                     </li>
                                  ))}
                                </ul>
                              </div>
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
            
            {/* Loading more indicator */}
            {loadingMore && (
              <div className="flex items-center justify-center py-6">
                <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600"></div>
                <span className="ml-2 text-gray-600">Loading more sites...</span>
              </div>
            )}
            
            {/* End of list indicator */}
            {!hasMore && sites.length > 0 && (
              <div className="text-center py-6 text-gray-500">
                <p>You've reached the end of the list!</p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );

  const StatsView = () => (
    <div className="space-y-6">
      {stats && (
        <>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Categories */}
            <div className="bg-white rounded-lg shadow p-6">
              <h3 className="text-lg font-medium text-gray-900 mb-4">📂 Categories</h3>
              <div className="space-y-3">
                {stats.categories.map((category) => (
                  <div key={category.name}>
                    <div className="flex justify-between text-sm text-gray-600 mb-1">
                      <span>{category.name}</span>
                      <span>{category.count}</span>
                    </div>
                    <div className="w-full bg-gray-200 rounded-full h-2">
                      <div
                        className="bg-blue-600 h-2 rounded-full"
                        style={{ width: `${(category.count / stats.total_sites) * 100}%` }}
                      ></div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Difficulty Distribution */}
            <div className="bg-white rounded-lg shadow p-6">
              <h3 className="text-lg font-medium text-gray-900 mb-4">📈 Difficulty Distribution</h3>
              <div className="space-y-3">
                {Object.entries(stats.difficulty_distribution).map(([difficulty, count]) => (
                  <div key={difficulty}>
                    <div className="flex justify-between text-sm text-gray-600 mb-1">
                      <span>{difficulty.charAt(0).toUpperCase() + difficulty.slice(1)}</span>
                      <span>{count}</span>
                    </div>
                    <div className="w-full bg-gray-200 rounded-full h-2">
                      <div
                        className={`h-2 rounded-full ${
                          difficulty === 'easy' ? 'bg-green-500' :
                          difficulty === 'medium' ? 'bg-yellow-500' :
                          difficulty === 'hard' ? 'bg-red-500' : 'bg-purple-500'
                        }`}
                        style={{ width: `${(count / stats.total_sites) * 100}%` }}
                      ></div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Implementation Status */}
          <div className="bg-white rounded-lg shadow p-6">
            <h3 className="text-lg font-medium text-gray-900 mb-4">🔧 Implementation Status</h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="text-center">
                <p className="text-3xl font-bold text-green-600">{stats.implementation_progress.signup_completed}</p>
                <p className="text-sm text-gray-600">Signup Completed</p>
              </div>
              <div className="text-center">
                <p className="text-3xl font-bold text-blue-600">{stats.implementation_progress.signin_completed}</p>
                <p className="text-sm text-gray-600">Signin Completed</p>
              </div>
              <div className="text-center">
                <p className="text-3xl font-bold text-yellow-600">{stats.implementation_progress.apikey_completed}</p>
                <p className="text-sm text-gray-600">API Key Completed</p>
              </div>
              <div className="text-center">
                <p className="text-3xl font-bold text-purple-600">{stats.implementation_progress.total_completed}</p>
                <p className="text-sm text-gray-600">Total Started</p>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="max-w-7xl mx-auto">
        <h1 className="text-3xl font-bold text-gray-900 mb-8">
          🗄️ FuzeKeys Sites Database
        </h1>
        
        <Tab.Group>
          <Tab.List className="flex space-x-1 rounded-xl bg-blue-900/20 p-1 mb-8">
            <Tab as={Fragment}>
              {({ selected }) => (
                <button
                  className={`w-full rounded-lg py-2.5 text-sm font-medium leading-5 text-blue-700 ring-white ring-opacity-60 ring-offset-2 ring-offset-blue-400 focus:outline-none focus:ring-2 ${
                    selected
                      ? 'bg-white shadow'
                      : 'text-blue-100 hover:bg-white/[0.12] hover:text-white'
                  }`}
                >
                  Sites Overview
                </button>
              )}
            </Tab>
            <Tab as={Fragment}>
              {({ selected }) => (
                <button
                  className={`w-full rounded-lg py-2.5 text-sm font-medium leading-5 text-blue-700 ring-white ring-opacity-60 ring-offset-2 ring-offset-blue-400 focus:outline-none focus:ring-2 ${
                    selected
                      ? 'bg-white shadow'
                      : 'text-blue-100 hover:bg-white/[0.12] hover:text-white'
                  }`}
                >
                  Statistics
                </button>
              )}
            </Tab>
          </Tab.List>
          <Tab.Panels>
            <Tab.Panel>
              <SitesOverview />
            </Tab.Panel>
            <Tab.Panel>
              <StatsView />
            </Tab.Panel>
          </Tab.Panels>
        </Tab.Group>
      </div>
    </div>
  );
};

export default SitesDatabase; 