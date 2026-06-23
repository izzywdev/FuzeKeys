// jest-dom adds helpful assertions to Jest for testing DOM elements
import '@testing-library/jest-dom';

// Mock IntersectionObserver globally for all tests
class MockIntersectionObserver implements IntersectionObserver {
  readonly root: Element | null = null;
  readonly rootMargin: string = '';
  readonly thresholds: ReadonlyArray<number> = [];

  constructor(public callback: IntersectionObserverCallback, public options?: IntersectionObserverInit) {
    // Store the callback and options
  }

  observe = jest.fn();
  unobserve = jest.fn();
  disconnect = jest.fn();
  takeRecords = jest.fn(() => []);
}

// Replace global IntersectionObserver
Object.defineProperty(window, 'IntersectionObserver', {
  writable: true,
  configurable: true,
  value: MockIntersectionObserver,
});

// Also set it on global for Node.js environment
Object.defineProperty(global, 'IntersectionObserver', {
  writable: true,
  configurable: true,
  value: MockIntersectionObserver,
});

// Mock other potentially missing browser APIs
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: jest.fn().mockImplementation(query => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: jest.fn(), // deprecated
    removeListener: jest.fn(), // deprecated
    addEventListener: jest.fn(),
    removeEventListener: jest.fn(),
    dispatchEvent: jest.fn(),
  })),
});

// Mock ResizeObserver if needed
Object.defineProperty(window, 'ResizeObserver', {
  writable: true,
  value: jest.fn().mockImplementation(() => ({
    observe: jest.fn(),
    unobserve: jest.fn(),
    disconnect: jest.fn(),
  })),
});

// Mock scrollTo
Object.defineProperty(window, 'scrollTo', {
  writable: true,
  value: jest.fn(),
});

// Suppress console warnings in tests
const originalConsoleError = console.error;
console.error = (...args: any[]) => {
  // Suppress known React warnings in tests
  if (
    typeof args[0] === 'string' &&
    args[0].includes('Warning: ReactDOM.render is no longer supported')
  ) {
    return;
  }
  originalConsoleError.call(console, ...args);
}; 