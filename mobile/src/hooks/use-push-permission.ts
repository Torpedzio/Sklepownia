import { useFocusEffect } from 'expo-router';
import { useCallback, useEffect, useState } from 'react';
import { AppState } from 'react-native';

import { enablePush, getPushPermission, pushBlocker, type PushPermission } from '@/lib/push';

/**
 * Whether this phone may show notifications, read again on focus and on coming back from the phone's settings.
 * `permission` is undefined while unknown and on devices that can't get them (`blocker`).
 */
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
