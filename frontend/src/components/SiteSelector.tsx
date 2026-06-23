import React, { useState, useEffect } from 'react';
import { XMarkIcon, MagnifyingGlassIcon } from '@heroicons/react/24/outline';

interface Site {
  id: string;
  name: string;
  url: string;
  icon: string;
  category: string;
  description: string;
  difficulty: 'Easy' | 'Medium' | 'Hard';
  features: string[];
}

interface Identity {
  id: number;
  name: string;
  description?: string;
}

interface SiteSelectorProps {
  onSiteSelect: (site: Site, identityId: number) => void;
  onClose: () => void;
}

const SiteSelector: React.FC<SiteSelectorProps> = ({ onSiteSelect, onClose }) => {
  const [selectedSite, setSelectedSite] = useState<Site | null>(null);
  const [identities, setIdentities] = useState<Identity[]>([]);
  const [selectedIdentity, setSelectedIdentity] = useState<number | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('all');
  const [loading, setLoading] = useState(true);

  // Mock sites data - in a real app, this would come from an API
  const sites: Site[] = [
    {
      id: 'google',
      name: 'Google',
      url: 'https://accounts.google.com',
      icon: '🔍',
      category: 'Search',
      description: 'Create Google accounts for Gmail, YouTube, and other Google services',
      difficulty: 'Medium',
      features: ['Email', 'Cloud Storage', 'YouTube', 'Maps']
    },
    {
      id: 'facebook',
      name: 'Facebook',
      url: 'https://facebook.com',
      icon: '📘',
      category: 'Social',
      description: 'Create Facebook accounts for social networking',
      difficulty: 'Hard',
      features: ['Social Network', 'Messaging', 'Groups', 'Pages']
    },
    {
      id: 'twitter',
      name: 'Twitter',
      url: 'https://twitter.com',
      icon: '🐦',
      category: 'Social',
      description: 'Create Twitter accounts for microblogging',
      difficulty: 'Medium',
      features: ['Microblogging', 'News', 'Trending', 'Direct Messages']
    },
    {
      id: 'linkedin',
      name: 'LinkedIn',
      url: 'https://linkedin.com',
      icon: '💼',
      category: 'Professional',
      description: 'Create LinkedIn accounts for professional networking',
      difficulty: 'Easy',
      features: ['Professional Network', 'Job Search', 'Business', 'Learning']
    }
  ];

  useEffect(() => {
      fetchIdentities();
  }, []);

  const fetchIdentities = async () => {
    try {
      setLoading(true);
      // Mock identities - in a real app, this would come from an API
      const mockIdentities: Identity[] = [
        { id: 1, name: 'John Doe', description: 'Primary identity' },
        { id: 2, name: 'Jane Smith', description: 'Secondary identity' },
        { id: 3, name: 'Bob Johnson', description: 'Test identity' }
      ];
      setIdentities(mockIdentities);
    } catch (error) {
      console.error('Failed to fetch identities:', error);
    } finally {
      setLoading(false);
    }
  };

  const uniqueCategories = Array.from(new Set(sites.map(site => site.category)));
  const categories = ['all'].concat(uniqueCategories);

  const filteredSites = sites.filter(site => {
    const matchesSearch = site.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
                         site.description.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesCategory = selectedCategory === 'all' || site.category === selectedCategory;
    return matchesSearch && matchesCategory;
  });

  const handleSiteSelect = (site: Site) => {
    setSelectedSite(site);
  };

  const handleConfirm = () => {
    if (selectedSite && selectedIdentity) {
      onSiteSelect(selectedSite, selectedIdentity);
    }
  };

  const getDifficultyColor = (difficulty: string) => {
    switch (difficulty) {
      case 'Easy': return 'text-green-600 bg-green-100';
      case 'Medium': return 'text-yellow-600 bg-yellow-100';
      case 'Hard': return 'text-red-600 bg-red-100';
      default: return 'text-gray-600 bg-gray-100';
    }
  };

  return (
    <div className="fixed inset-0 bg-gray-600 bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg w-full max-w-4xl mx-4 max-h-[90vh] overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-gray-200">
          <h2 className="text-xl font-semibold text-gray-900">Select Site and Identity</h2>
              <button
                onClick={onClose}
            className="text-gray-400 hover:text-gray-600"
          >
            <XMarkIcon className="h-6 w-6" />
          </button>
        </div>

        <div className="flex h-[70vh]">
          {/* Site Selection */}
          <div className="w-1/2 p-6 border-r border-gray-200">
            <h3 className="text-lg font-medium text-gray-900 mb-4">Choose a Site</h3>
            
            {/* Search and Filter */}
            <div className="space-y-4 mb-6">
              <div className="relative">
                <MagnifyingGlassIcon className="h-5 w-5 absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400" />
                <input
                  type="text"
                  placeholder="Search sites..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                />
              </div>
              
              <select
                value={selectedCategory}
                onChange={(e) => setSelectedCategory(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent"
              >
                {categories.map(category => (
                  <option key={category} value={category}>
                    {category === 'all' ? 'All Categories' : category}
                  </option>
                ))}
              </select>
        </div>

            {/* Sites List */}
            <div className="space-y-3 overflow-y-auto max-h-96">
              {filteredSites.map(site => (
                        <div
                          key={site.id}
                          onClick={() => handleSiteSelect(site)}
                  className={`p-4 border rounded-lg cursor-pointer transition-colors ${
                    selectedSite?.id === site.id
                      ? 'border-primary-500 bg-primary-50'
                      : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
                  }`}
                >
                  <div className="flex items-start space-x-3">
                    <span className="text-2xl">{site.icon}</span>
                            <div className="flex-1">
                      <div className="flex items-center justify-between">
                        <h4 className="font-medium text-gray-900">{site.name}</h4>
                        <span className={`px-2 py-1 rounded-full text-xs font-medium ${getDifficultyColor(site.difficulty)}`}>
                              {site.difficulty}
                            </span>
                          </div>
                      <p className="text-sm text-gray-600 mt-1">{site.description}</p>
                      <div className="flex flex-wrap gap-1 mt-2">
                        {site.features.slice(0, 3).map(feature => (
                          <span key={feature} className="px-2 py-1 bg-gray-100 text-gray-600 text-xs rounded">
                                {feature}
                          </span>
                        ))}
                        {site.features.length > 3 && (
                          <span className="px-2 py-1 bg-gray-100 text-gray-600 text-xs rounded">
                            +{site.features.length - 3} more
                          </span>
                            )}
                          </div>
                        </div>
                  </div>
                </div>
              ))}
                    </div>
                  </div>

          {/* Identity Selection */}
          <div className="w-1/2 p-6">
            <h3 className="text-lg font-medium text-gray-900 mb-4">Choose an Identity</h3>

              {loading ? (
              <div className="flex items-center justify-center h-32">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600"></div>
                </div>
              ) : (
              <div className="space-y-3 overflow-y-auto max-h-96">
                  {identities.map(identity => (
                    <div
                      key={identity.id}
                    onClick={() => setSelectedIdentity(identity.id)}
                    className={`p-4 border rounded-lg cursor-pointer transition-colors ${
                        selectedIdentity === identity.id
                        ? 'border-primary-500 bg-primary-50'
                        : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
                    }`}
                  >
                    <h4 className="font-medium text-gray-900">{identity.name}</h4>
                          {identity.description && (
                      <p className="text-sm text-gray-600 mt-1">{identity.description}</p>
                    )}
                    </div>
                  ))}
                </div>
              )}

            {/* Selected Site Info */}
            {selectedSite && (
              <div className="mt-6 p-4 bg-gray-50 rounded-lg">
                <h4 className="font-medium text-gray-900 mb-2">Selected Site</h4>
                <div className="flex items-center space-x-2">
                  <span className="text-xl">{selectedSite.icon}</span>
                  <span className="font-medium">{selectedSite.name}</span>
                </div>
                <p className="text-sm text-gray-600 mt-1">{selectedSite.description}</p>
              </div>
            )}
              </div>
            </div>

        {/* Footer */}
        <div className="flex items-center justify-between p-6 border-t border-gray-200">
              <div className="text-sm text-gray-600">
            {selectedSite && selectedIdentity
              ? `Ready to create ${selectedSite.name} account with ${identities.find(i => i.id === selectedIdentity)?.name}`
              : 'Select both a site and an identity to continue'
            }
              </div>
              <div className="flex space-x-3">
                <button
              onClick={onClose}
                  className="px-4 py-2 text-gray-700 bg-gray-200 rounded-lg hover:bg-gray-300"
                >
              Cancel
                </button>
                <button
              onClick={handleConfirm}
              disabled={!selectedSite || !selectedIdentity}
              className="btn-primary disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Create Account
                </button>
              </div>
        </div>
      </div>
    </div>
  );
};

export default SiteSelector; 