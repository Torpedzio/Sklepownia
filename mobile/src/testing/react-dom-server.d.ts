// Tests render +html.tsx to a string the way the server does; the app has no @types/react-dom.
declare module 'react-dom/server' {
  import type { ReactNode } from 'react';

  export function renderToStaticMarkup(element: ReactNode): string;
}
