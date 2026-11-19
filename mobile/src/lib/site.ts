import { origin } from 'expo-server';

/**
 * Absolute site address without a trailing slash (canonical, previews, sitemap.xml). `SITE_URL` overrides the
 * request's address where the server can't see it, e.g. behind a proxy. Server only.
 */
export function siteUrl() {
  const configured = process.env.SITE_URL;
  if (configured) return configured.replace(/\/+$/, '');
  try {
    return (origin() ?? '').replace(/\/+$/, '');
  } catch {
    return '';
  }
}
