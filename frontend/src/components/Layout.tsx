import React from 'react';
import { Outlet, Link, useLocation } from 'react-router-dom';

const Layout: React.FC = () => {
  const location = useLocation();
  
  const navigation = [
    { name: 'Dashboard', href: '/dashboard' },
    { name: 'Identities', href: '/identities' },
    { name: 'Accounts', href: '/accounts' },
    { name: 'Sites Database', href: '/sites' },
    { name: 'Chat', href: '/chat' },
  ];

  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between h-16">
            <div className="flex items-center">
              <h1 className="text-xl font-bold text-primary-600">FuzeKeys</h1>
              <span className="ml-2 text-sm text-gray-500 bg-gray-100 px-2 py-1 rounded">Demo</span>
            </div>
            
            <div className="flex items-center space-x-8">
              {navigation.map((item) => (
                <Link
                  key={item.name}
                  to={item.href}
                  className={`${
                    location.pathname === item.href
                      ? 'text-primary-600 border-primary-600'
                      : 'text-gray-500 hover:text-gray-700 border-transparent hover:border-gray-300'
                  } inline-flex items-center px-1 pt-1 border-b-2 text-sm font-medium transition-colors duration-200`}
                >
                  {item.name}
                </Link>
              ))}
            </div>
          </div>
        </div>
      </nav>
      
      <main className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
        <Outlet />
      </main>
    </div>
  );
};

export default Layout; 