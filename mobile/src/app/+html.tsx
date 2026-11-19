import { ScrollViewStyleReset, useServerDocumentContext } from 'expo-router/html';
import type { PropsWithChildren } from 'react';

import { Brand } from '@/constants/brand';
import { documentTitle, HomeTitle, publicPage } from '@/constants/pages';
import { Colors, colorVariablesCss } from '@/constants/theme';
import { siteUrl } from '@/lib/site';
import { viewportOfRequest } from '@/lib/viewport';

/**
 * The web page shell, server-rendered per request, never in the browser: <head> for search engines and previews
 * (constants/pages.ts), colors for the visitor's mode before JS runs, the assumed window size (lib/viewport.ts).
 */
export default function Root({ children, pathname = '/' }: PropsWithChildren<{ pathname?: string }>) {
  const { htmlAttributes, bodyAttributes, headNodes, bodyNodes } = useServerDocumentContext();
  const page = publicPage(pathname);
  const site = siteUrl();
  const title = documentTitle(pathname);
  const url = page && site + page.path;

  return (
    <html {...htmlAttributes} lang="pl" data-viewport={viewportOfRequest()}>
      <head>
        <meta charSet="utf-8" />
        <meta httpEquiv="X-UA-Compatible" content="IE=edge" />
        <meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no" />
        <title>{title}</title>
        {page ? <meta name="description" content={page.description} /> : null}
        {/* The app behind sign-in and unknown addresses stay out of search results. */}
        {page?.indexed ? <link rel="canonical" href={url} /> : <meta name="robots" content="noindex" />}
        {page?.indexed ? (
          <>
            <meta property="og:type" content="website" />
            <meta property="og:site_name" content={Brand.name} />
            <meta property="og:locale" content="pl_PL" />
            <meta property="og:url" content={url} />
            <meta property="og:title" content={page.path === '/' ? HomeTitle : page.title} />
            <meta property="og:description" content={page.description} />
            <meta property="og:image" content={`${site}/og.png`} />
            <meta property="og:image:width" content="1200" />
            <meta property="og:image:height" content="630" />
            <meta property="og:image:alt" content={`${Brand.name}: ${Brand.tagline.toLowerCase()}`} />
            <meta name="twitter:card" content="summary_large_image" />
          </>
        ) : null}
        <meta name="theme-color" media="(prefers-color-scheme: light)" content={Colors.light.background} />
        <meta name="theme-color" media="(prefers-color-scheme: dark)" content={Colors.dark.background} />
        <link rel="icon" href="/favicon.svg" type="image/svg+xml" />
        <link rel="apple-touch-icon" href="/apple-touch-icon.png" />
        <ScrollViewStyleReset />
        <style
          id="theme-colors"
          dangerouslySetInnerHTML={{ __html: `${colorVariablesCss()}body{background-color:var(--color-background)}` }}
        />
        {page?.path === '/' ? (
          <script
            type="application/ld+json"
            dangerouslySetInnerHTML={{
              __html: JSON.stringify({
                '@context': 'https://schema.org',
                '@graph': [
                  { '@type': 'Organization', name: Brand.name, url: `${site}/`, logo: `${site}/apple-touch-icon.png` },
                  { '@type': 'WebSite', name: Brand.name, url: `${site}/`, inLanguage: 'pl-PL' },
                ],
              }),
            }}
          />
        ) : null}
        {headNodes}
      </head>
      <body {...bodyAttributes}>
        {children}
        {bodyNodes}
      </body>
    </html>
  );
}
