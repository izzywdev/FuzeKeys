/**
 * Tests for SitesDatabase component.
 * 
 * This test suite covers:
 * - Component rendering and loading states
 * - API data fetching and error handling
 * - Infinite scroll functionality
 * - Filtering and search functionality
 * - User interactions and navigation
 */

import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import '@testing-library/jest-dom';
import SitesDatabase from '../SitesDatabase';

// Mock fetch globally
const mockFetch = jest.fn();
global.fetch = mockFetch;

// Test data
const mockSitesData = [
  {
    id: 1,
    name: 'google',
    display_name: 'Google',
    url: 'https://google.com',
    logo_url: 'https://www.google.com/favicon.ico',
    category: 'tech-giant',
    description: 'Search engine and tech giant',
    signup_difficulty: 'extreme',
    signin_difficulty: 'hard',
    apikey_difficulty: 'hard',
    overall_difficulty: 'extreme',
    requires_email_verification: true,
    requires_phone_verification: true,
    requires_sms_verification: false,
    requires_authenticator: true,
    has_captcha: true,
    captcha_type: 'recaptcha',
    anti_bot_techniques: ['fingerprinting', 'behavioral_analysis'],
    signup_status: 'in_progress',
    signin_status: 'completed',
    apikey_status: 'not_started',
    implementation_progress: 33.3,
    priority: 100,
    estimated_hours: 40,
    has_official_api: true,
    api_documentation_url: 'https://developers.google.com',
    api_rate_limits: 'Varies by service',
    notes: 'Complex authentication flow',
    created_at: '2024-01-01T00:00:00Z'
  },
  {
    id: 2,
    name: 'github',
    display_name: 'GitHub',
    url: 'https://github.com',
    logo_url: 'https://github.com/favicon.ico',
    category: 'developer-tools',
    description: 'Code hosting and collaboration platform',
    signup_difficulty: 'easy',
    signin_difficulty: 'easy',
    apikey_difficulty: 'easy',
    overall_difficulty: 'easy',
    requires_email_verification: true,
    requires_phone_verification: false,
    requires_sms_verification: false,
    requires_authenticator: false,
    has_captcha: false,
    captcha_type: null,
    anti_bot_techniques: [],
    signup_status: 'completed',
    signin_status: 'completed',
    apikey_status: 'completed',
    implementation_progress: 100.0,
    priority: 85,
    estimated_hours: 8,
    has_official_api: true,
    api_documentation_url: 'https://docs.github.com/en/rest',
    api_rate_limits: '5000 requests/hour',
    notes: 'Well documented API',
    created_at: '2024-01-02T00:00:00Z'
  }
];

const mockStatsData = {
  total_sites: 199,
  categories: [
    { name: 'tech-giant', count: 10 },
    { name: 'developer-tools', count: 25 },
    { name: 'cloud-provider', count: 15 }
  ],
  implementation_progress: {
    signup_completed: 45,
    signin_completed: 52,
    apikey_completed: 38,
    total_completed: 67
  },
  difficulty_distribution: {
    easy: 45,
    medium: 89,
    hard: 52,
    extreme: 13
  },
  estimated_total_hours: 2847
};

// Wrapper component for routing
const TestWrapper: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <BrowserRouter>
    {children}
  </BrowserRouter>
);

describe('SitesDatabase Component', () => {
  beforeEach(() => {
    // Clear all mocks before each test
    mockFetch.mockClear();
    jest.clearAllMocks();
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  describe('Initial Loading and Rendering', () => {
    it('renders loading state initially', async () => {
      // Mock pending fetch requests that don't resolve immediately
      let resolveSites: (value: any) => void;
      let resolveStats: (value: any) => void;
      
      const sitesPromise = new Promise(resolve => { resolveSites = resolve; });
      const statsPromise = new Promise(resolve => { resolveStats = resolve; });

      mockFetch
        .mockReturnValueOnce(sitesPromise)
        .mockReturnValueOnce(statsPromise);

      render(
        <TestWrapper>
          <SitesDatabase />
        </TestWrapper>
      );

      expect(screen.getByText('Loading sites...')).toBeInTheDocument();
      
      // Clean up by resolving the promises
      resolveSites!({ ok: true, json: async () => [] });
      resolveStats!({ ok: true, json: async () => mockStatsData });
    });

    it('renders sites data after successful fetch', async () => {
      // Mock successful API responses
      mockFetch
        .mockResolvedValueOnce({
          ok: true,
          json: async () => mockSitesData
        })
        .mockResolvedValueOnce({
          ok: true,
          json: async () => mockStatsData
        });

      render(
        <TestWrapper>
          <SitesDatabase />
        </TestWrapper>
      );

      // Wait for data to load and check if component renders
      await waitFor(() => {
        expect(screen.getByText('Google')).toBeInTheDocument();
      }, { timeout: 5000 });
      
      expect(screen.getByText('GitHub')).toBeInTheDocument();

      // Check that sites are displayed with correct data
      expect(screen.getByText('Search engine and tech giant')).toBeInTheDocument();
      expect(screen.getByText('Code hosting and collaboration platform')).toBeInTheDocument();
      
      // Check priority indicators
      expect(screen.getByText('Priority: 100')).toBeInTheDocument();
      expect(screen.getByText('Priority: 85')).toBeInTheDocument();
    });

    it('handles API errors gracefully', async () => {
      mockFetch.mockRejectedValue(new Error('Network error'));

      render(
        <TestWrapper>
          <SitesDatabase />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText(/error/i)).toBeInTheDocument();
      }, { timeout: 5000 });
    });
  });

  describe('API Integration', () => {
    it('makes correct API calls on component mount', async () => {
      mockFetch
        .mockResolvedValueOnce({
          ok: true,
          json: async () => mockSitesData
        })
        .mockResolvedValueOnce({
          ok: true,
          json: async () => mockStatsData
        });

      render(
        <TestWrapper>
          <SitesDatabase />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(mockFetch).toHaveBeenCalledWith(
          expect.stringContaining('api/v1/sites')
        );
  });

      // Verify sites API call
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('skip=0&limit=20')
      );

      // Verify stats API call
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('api/v1/sites/stats/overview')
      );
      });
      
    it('includes correct pagination and sorting parameters', async () => {
      mockFetch
        .mockResolvedValueOnce({
          ok: true,
          json: async () => mockSitesData
        })
        .mockResolvedValueOnce({
          ok: true,
          json: async () => mockStatsData
        });

      render(
        <TestWrapper>
          <SitesDatabase />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(mockFetch).toHaveBeenCalledWith(
          expect.stringContaining('sort_by=priority&sort_order=desc')
        );
      });
    });
  });

  describe('IntersectionObserver Integration', () => {
    it('creates IntersectionObserver for infinite scroll', async () => {
      const IntersectionObserverSpy = jest.spyOn(window, 'IntersectionObserver');
      
      mockFetch
        .mockResolvedValueOnce({
          ok: true,
          json: async () => mockSitesData
        })
        .mockResolvedValueOnce({
          ok: true,
          json: async () => mockStatsData
        });

      render(
        <TestWrapper>
          <SitesDatabase />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(IntersectionObserverSpy).toHaveBeenCalled();
    });

      IntersectionObserverSpy.mockRestore();
    });
  });

  describe('Search and Filtering', () => {
    it('renders search input', async () => {
      mockFetch
        .mockResolvedValue({
          ok: true,
          json: async () => mockSitesData
        });

      render(
        <TestWrapper>
          <SitesDatabase />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByPlaceholderText(/search/i)).toBeInTheDocument();
      });
    });

    it('triggers search when input changes', async () => {
      mockFetch
        .mockResolvedValue({
          ok: true,
          json: async () => mockSitesData
        });

      render(
        <TestWrapper>
          <SitesDatabase />
        </TestWrapper>
      );

      // Wait for initial render
      await waitFor(() => {
        expect(screen.getByPlaceholderText(/search/i)).toBeInTheDocument();
      });

      const searchInput = screen.getByPlaceholderText(/search/i);
      fireEvent.change(searchInput, { target: { value: 'google' } });

      // Wait for debounced search to trigger
      await waitFor(() => {
        expect(mockFetch).toHaveBeenCalledWith(
          expect.stringContaining('search=google')
        );
      }, { timeout: 1000 });
    });
  });
}); 