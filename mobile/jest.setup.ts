// Screens read safe-area insets; the library ships a mock with zero insets for tests.
jest.mock('react-native-safe-area-context', () => require('react-native-safe-area-context/jest/mock').default);

// Screens share loaded data between renders; every test starts without it (before, not after: the previous
// test's screens are unmounted by then). Required here, not imported, so it's the cache the test's modules use.
beforeEach(() => {
  require('@/lib/query-cache').clearQueryCache();
});
