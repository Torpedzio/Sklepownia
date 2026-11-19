import { useRef, useState, type ComponentRef } from 'react';
import { Platform, View, type LayoutChangeEvent } from 'react-native';

import { Spacing } from '@/constants/theme';
import { useWindowDimensions } from '@/hooks/use-window-dimensions';

/**
 * Lets a section in the centered column reach the page edges: `columnRef` and `onColumnLayout` go on a View in the
 * column, `width` and `marginLeft: -inset` on the child. The web measures the column (its scrollbar narrows the page).
 */
export function useFullBleed() {
  const { width: windowWidth } = useWindowDimensions();
  const columnRef = useRef<ComponentRef<typeof View>>(null);
  const [column, setColumn] = useState<{ left: number; width: number }>();

  function onColumnLayout(event: LayoutChangeEvent) {
    const columnWidth = event.nativeEvent.layout.width;
    if (Platform.OS === 'web') {
      columnRef.current?.measureInWindow((left) => setColumn({ left, width: columnWidth }));
    } else {
      setColumn({ left: (windowWidth - columnWidth) / 2, width: columnWidth });
    }
  }

  const inset = column?.left ?? Spacing.four;
  return { columnRef, onColumnLayout, inset, width: column ? column.width + inset * 2 : windowWidth };
}
