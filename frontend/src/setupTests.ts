// jest-dom adds helpful assertions to Jest for testing DOM elements
import '@testing-library/jest-dom';

// Mock IntersectionObserver globally for all tests.
//
// Two constraints shape this:
//  * It must NOT be an ES6 `class`. Tests wrap it with
//    jest.spyOn(window, 'IntersectionObserver'), and the spy calls the original
//    through .apply(), which a class constructor rejects with
//    "Class constructor cannot be invoked without 'new'".
//  * It must NOT be a jest.fn().mockImplementation(...). react-scripts enables
//    `resetMocks` by default, which strips mock implementations before every
//    test and would leave `new IntersectionObserver()` returning a bare {}.
// An ES5 function constructor satisfies both.
function MockIntersectionObserver(
  this: any,
  callback: IntersectionObserverCallback,
  options?: IntersectionObserverInit
) {
  this.root = options?.root ?? null;
  this.rootMargin = options?.rootMargin ?? '';
  this.thresholds = [];
  this.callback = callback;
  this.observe = jest.fn();
  this.unobserve = jest.fn();
  this.disconnect = jest.fn();
  this.takeRecords = jest.fn(() => []);
}

const IntersectionObserverMock =
  MockIntersectionObserver as unknown as typeof IntersectionObserver;

// Replace global IntersectionObserver
Object.defineProperty(window, 'IntersectionObserver', {
  writable: true,
  configurable: true,
  value: IntersectionObserverMock,
});

// Also set it on global for Node.js environment
Object.defineProperty(global, 'IntersectionObserver', {
  writable: true,
  configurable: true,
  value: IntersectionObserverMock,
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