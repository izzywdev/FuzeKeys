import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';

interface Identity {
  id: number;
  name: string;
  description: string;
  firstName: string;
  lastName: string;
  email: string;
  phone?: string;
  dateOfBirth?: string;
  gender?: string;
  address?: {
    line1?: string;
    line2?: string;
    city?: string;
    state?: string;
    zipCode?: string;
    country?: string;
  };
  profession: string;
  company?: string;
  bio?: string;
  location: string;
  created_at: string;
  accountsCount: number;
}

const Identities: React.FC = () => {
  const navigate = useNavigate();
  const [identities] = useState<Identity[]>([
    {
      id: 1,
      name: "Professional Identity",
      description: "For business and professional accounts",
      firstName: "Alex",
      lastName: "Johnson",
      email: "alex.johnson.pro@email.com",
      phone: "+1 (555) 123-4567",
      dateOfBirth: "1990-05-15",
      gender: "prefer-not-to-say",
      address: {
        line1: "123 Main Street",
        city: "San Francisco",
        state: "CA",
        zipCode: "94105",
        country: "US"
      },
      profession: "Software Developer",
      company: "TechCorp Inc.",
      bio: "Brief description about yourself...",
      location: "San Francisco, CA",
      created_at: "2024-01-15",
      accountsCount: 5
    },
    {
      id: 2,
      name: "Personal Identity",
      description: "For social media and personal accounts",
      firstName: "Alex",
      lastName: "J",
      email: "alexj.personal@email.com",
      phone: "+1 (555) 123-4567",
      dateOfBirth: "1990-05-15",
      gender: "non-binary",
      address: {
        line1: "123 Main Street",
        city: "California",
        state: "CA",
        zipCode: "94105",
        country: "US"
      },
      profession: "Tech Enthusiast",
      location: "California, USA",
      created_at: "2024-01-20",
      accountsCount: 3
    }
  ]);

  const [selectedIdentity, setSelectedIdentity] = useState<Identity | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);

  const handleAccountCountClick = (identityId: number, identityName: string) => {
    navigate(`/accounts?identity=${identityId}&name=${encodeURIComponent(identityName)}`);
  };

  return (
    <div className="px-4 py-6 sm:px-0">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 mb-2">Digital Identities</h1>
          <p className="text-gray-600">Manage your encrypted digital identities for different use cases</p>
        </div>
        <button 
          onClick={() => setShowCreateModal(true)}
          className="btn-primary"
        >
          + Create Identity
        </button>
      </div>

      {/* Demo Notice */}
      <div className="mb-6 bg-blue-50 border border-blue-200 rounded-lg p-4">
        <h3 className="text-sm font-semibold text-blue-900 mb-1">🎮 Demo Mode</h3>
        <p className="text-sm text-blue-800">
          In the full version, all identity data would be encrypted with your master key and stored securely.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-6">
        {identities.map((identity) => (
          <div key={identity.id} className="card hover:shadow-lg transition-shadow duration-200">
            <div className="flex justify-between items-start mb-4">
              <div>
                <h3 className="text-lg font-semibold text-gray-900">{identity.name}</h3>
                <p className="text-gray-600 text-sm">{identity.description}</p>
              </div>
              <button
                onClick={() => handleAccountCountClick(identity.id, identity.name)}
                className="bg-green-100 text-green-800 text-xs px-2 py-1 rounded-full hover:bg-green-200 transition-colors cursor-pointer"
                title={`View ${identity.accountsCount} accounts for ${identity.name}`}
              >
                {identity.accountsCount} accounts
              </button>
            </div>
            
            <div className="space-y-2 mb-4">
              <div className="flex justify-between">
                <span className="text-sm text-gray-500">Name:</span>
                <span className="text-sm font-medium">{identity.firstName} {identity.lastName}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-sm text-gray-500">Email:</span>
                <span className="text-sm font-medium">{identity.email}</span>
              </div>
              {identity.phone && (
                <div className="flex justify-between">
                  <span className="text-sm text-gray-500">Phone:</span>
                  <span className="text-sm font-medium">{identity.phone}</span>
                </div>
              )}
              <div className="flex justify-between">
                <span className="text-sm text-gray-500">Profession:</span>
                <span className="text-sm font-medium">{identity.profession}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-sm text-gray-500">Location:</span>
                <span className="text-sm font-medium">{identity.location}</span>
              </div>
            </div>
            
            <div className="flex justify-between items-center pt-4 border-t border-gray-200">
              <span className="text-xs text-gray-500">
                Created {new Date(identity.created_at).toLocaleDateString()}
              </span>
              <button 
                onClick={() => setSelectedIdentity(identity)}
                className="text-primary-600 hover:text-primary-700 text-sm font-medium"
              >
                View Details
              </button>
            </div>
          </div>
        ))}
      </div>

      {/* Create Identity Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-gray-600 bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-full max-w-2xl mx-4 max-h-[90vh] overflow-y-auto">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">Create New Identity</h3>
            
            <div className="space-y-4">
              {/* Basic Information */}
              <div className="border-b border-gray-200 pb-4">
                <h4 className="text-md font-medium text-gray-900 mb-3">Basic Information</h4>
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Identity Name *</label>
                    <input type="text" className="input-field" placeholder="e.g., Work Identity" />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
                    <input type="text" className="input-field" placeholder="e.g., For professional accounts" />
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">First Name *</label>
                      <input type="text" className="input-field" placeholder="John" />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">Last Name *</label>
                      <input type="text" className="input-field" placeholder="Doe" />
                    </div>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Email *</label>
                    <input type="email" className="input-field" placeholder="john.doe@example.com" />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Phone Number</label>
                    <input type="tel" className="input-field" placeholder="+1 (555) 123-4567" />
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">Date of Birth</label>
                      <input type="date" className="input-field" />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">Gender</label>
                      <select className="input-field">
                        <option value="">Select Gender</option>
                        <option value="male">Male</option>
                        <option value="female">Female</option>
                        <option value="non-binary">Non-binary</option>
                        <option value="prefer-not-to-say">Prefer not to say</option>
                        <option value="other">Other</option>
                      </select>
                    </div>
                  </div>
                </div>
              </div>

              {/* Address Information */}
              <div className="border-b border-gray-200 pb-4">
                <h4 className="text-md font-medium text-gray-900 mb-3">Address Information</h4>
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Address Line 1</label>
                    <input type="text" className="input-field" placeholder="123 Main Street" />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Address Line 2</label>
                    <input type="text" className="input-field" placeholder="Apt 4B (optional)" />
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">City</label>
                      <input type="text" className="input-field" placeholder="San Francisco" />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">State/Province</label>
                      <input type="text" className="input-field" placeholder="CA" />
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">ZIP/Postal Code</label>
                      <input type="text" className="input-field" placeholder="94105" />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">Country</label>
                      <select className="input-field">
                        <option value="">Select Country</option>
                        <option value="US">United States</option>
                        <option value="CA">Canada</option>
                        <option value="GB">United Kingdom</option>
                        <option value="AU">Australia</option>
                        <option value="DE">Germany</option>
                        <option value="FR">France</option>
                        <option value="JP">Japan</option>
                        <option value="other">Other</option>
                      </select>
                    </div>
                  </div>
                </div>
              </div>

              {/* Professional Information */}
              <div>
                <h4 className="text-md font-medium text-gray-900 mb-3">Professional Information</h4>
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Profession</label>
                    <input type="text" className="input-field" placeholder="Software Developer" />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Company</label>
                    <input type="text" className="input-field" placeholder="TechCorp Inc." />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Bio</label>
                    <textarea 
                      className="input-field" 
                      rows={3} 
                      placeholder="Brief description about yourself..."
                    ></textarea>
                  </div>
                </div>
              </div>
            </div>

            <div className="flex justify-end space-x-3 mt-6 pt-4 border-t border-gray-200">
              <button 
                onClick={() => setShowCreateModal(false)}
                className="px-4 py-2 text-gray-700 bg-gray-200 rounded-lg hover:bg-gray-300"
              >
                Cancel
              </button>
              <button 
                onClick={() => {
                  setShowCreateModal(false);
                  // In real app, would create the identity with all collected data
                }}
                className="btn-primary"
              >
                Create Identity
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Identity Details Modal */}
      {selectedIdentity && (
        <div className="fixed inset-0 bg-gray-600 bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-full max-w-2xl mx-4 max-h-[90vh] overflow-y-auto">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">{selectedIdentity.name}</h3>
            
            <div className="space-y-6">
              {/* Basic Information */}
              <div>
                <h4 className="text-md font-medium text-gray-900 mb-3 border-b border-gray-200 pb-2">Basic Information</h4>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700">Full Name</label>
                    <p className="text-gray-900">{selectedIdentity.firstName} {selectedIdentity.lastName}</p>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700">Email</label>
                    <p className="text-gray-900">{selectedIdentity.email}</p>
                  </div>
                  {selectedIdentity.phone && (
                    <div>
                      <label className="block text-sm font-medium text-gray-700">Phone</label>
                      <p className="text-gray-900">{selectedIdentity.phone}</p>
                    </div>
                  )}
                  {selectedIdentity.dateOfBirth && (
                    <div>
                      <label className="block text-sm font-medium text-gray-700">Date of Birth</label>
                      <p className="text-gray-900">{new Date(selectedIdentity.dateOfBirth).toLocaleDateString()}</p>
                    </div>
                  )}
                  {selectedIdentity.gender && (
                    <div>
                      <label className="block text-sm font-medium text-gray-700">Gender</label>
                      <p className="text-gray-900 capitalize">{selectedIdentity.gender.replace('-', ' ')}</p>
                    </div>
                  )}
                </div>
              </div>

              {/* Address Information */}
              {selectedIdentity.address && (
                <div>
                  <h4 className="text-md font-medium text-gray-900 mb-3 border-b border-gray-200 pb-2">Address</h4>
                  <div className="space-y-2">
                    {selectedIdentity.address.line1 && (
                      <p className="text-gray-900">{selectedIdentity.address.line1}</p>
                    )}
                    {selectedIdentity.address.line2 && (
                      <p className="text-gray-900">{selectedIdentity.address.line2}</p>
                    )}
                    <p className="text-gray-900">
                      {[
                        selectedIdentity.address.city,
                        selectedIdentity.address.state,
                        selectedIdentity.address.zipCode
                      ].filter(Boolean).join(', ')}
                    </p>
                    {selectedIdentity.address.country && (
                      <p className="text-gray-900">{selectedIdentity.address.country}</p>
                    )}
                  </div>
                </div>
              )}

              {/* Professional Information */}
              <div>
                <h4 className="text-md font-medium text-gray-900 mb-3 border-b border-gray-200 pb-2">Professional</h4>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700">Profession</label>
                    <p className="text-gray-900">{selectedIdentity.profession}</p>
                  </div>
                  {selectedIdentity.company && (
                    <div>
                      <label className="block text-sm font-medium text-gray-700">Company</label>
                      <p className="text-gray-900">{selectedIdentity.company}</p>
                    </div>
                  )}
                </div>
                {selectedIdentity.bio && (
                  <div className="mt-3">
                    <label className="block text-sm font-medium text-gray-700">Bio</label>
                    <p className="text-gray-900">{selectedIdentity.bio}</p>
                  </div>
                )}
              </div>

              {/* Account Information */}
              <div>
                <h4 className="text-md font-medium text-gray-900 mb-3 border-b border-gray-200 pb-2">Account Details</h4>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700">Active Accounts</label>
                    <p className="text-gray-900">{selectedIdentity.accountsCount} accounts</p>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700">Created</label>
                    <p className="text-gray-900">{new Date(selectedIdentity.created_at).toLocaleDateString()}</p>
                  </div>
                </div>
              </div>
            </div>
            
            <div className="flex justify-end space-x-3 mt-6 pt-4 border-t border-gray-200">
              <button 
                onClick={() => setSelectedIdentity(null)}
                className="px-4 py-2 text-gray-700 bg-gray-200 rounded-lg hover:bg-gray-300"
              >
                Close
              </button>
              <button className="btn-primary">
                Edit Identity
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default Identities; 