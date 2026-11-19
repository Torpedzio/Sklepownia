import { useFocusEffect } from 'expo-router';
import { useCallback, useEffect, useState } from 'react';
import { AppState } from 'react-native';

import { enablePush, getPushPermission, pushBlocker, type PushPermission } from '@/lib/push';

/** Re-read on focus and on return from the phone's settings. `permission` is undefined while unknown or `blocker` is set. */
export function usePushPermission() {
  const blocker = pushBlocker();
  const [state, setState] = useState<{ permission: PushPermission; canAskAgain: boolean }>();

  const load = useCallback(async () => {
    if (!blocker) setState(await getPushPermission());
  }, [blocker]);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load]),
  );

  useEffect(() => {
    const subscription = AppState.addEventListener('change', (next) => {
      if (next === 'active') load();
    });
    return () => subscription.remove();
  }, [load]);

  const enable = useCallback(async () => {
    const permission = await enablePush();
    await load();
    return permission;
  }, [load]);

  return { blocker, permission: state?.permission, canAskAgain: state?.canAskAgain ?? false, enable };
}
