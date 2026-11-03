import { useEffect, useRef, useState, type ComponentRef, type PropsWithChildren } from 'react';
import { Keyboard, Platform, StyleSheet, View } from 'react-native';

/**
 * Shrinks to stay above the software keyboard on Android, where edge-to-edge apps are not
 * resized when the keyboard opens. A scroll view inside then keeps the focused field in view.
 * iOS scroll views handle this themselves with `automaticallyAdjustKeyboardInsets`.
 */
export function KeyboardArea({ children }: PropsWithChildren) {
  const area = useRef<ComponentRef<typeof View>>(null);
  const [overlap, setOverlap] = useState(0);

  useEffect(() => {
    if (Platform.OS !== 'android') return;
    const show = Keyboard.addListener('keyboardDidShow', (event) => {
      // Measure against this area, not the screen: tab bars and headers may already sit below it.
      area.current?.measureInWindow((_x, y, _width, height) =>
        setOverlap(Math.max(y + height - event.endCoordinates.screenY, 0)),
      );
    });
    const hide = Keyboard.addListener('keyboardDidHide', () => setOverlap(0));
    return () => {
      show.remove();
      hide.remove();
    };
  }, []);

  return (
    <View ref={area} style={[styles.area, { paddingBottom: overlap }]}>
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  area: {
    flex: 1,
  },
});
