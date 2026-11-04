import { useRef, useState, type ComponentRef } from 'react';
import { Platform, useWindowDimensions, View, type LayoutChangeEvent } from 'react-native';

import { Spacing } from '@/constants/theme';

/**
 * Lets a section inside the centered page column reach the page edges. Put `columnRef` and `onColumnLayout`
 * on a View in the column, then give the full-width child `width` and `marginLeft: -inset`;
 * `inset` is also where the column starts, for lining content up with the rest of the page.
 * On the web the page is narrower than the window by its scrollbar, so the column is measured there.
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
