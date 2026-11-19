// The library's mock gives zero safe-area insets.
jest.mock('react-native-safe-area-context', () => require('react-native-safe-area-context/jest/mock').default);

// Every test starts with an empty query cache (before, not after: the previous test's screens are unmounted by
// then). Required, not imported, so it's the module instance the test's modules use.
beforeEach(() => {
  require('@/lib/query-cache').clearQueryCache();
});
