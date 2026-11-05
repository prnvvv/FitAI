/**
 * Return `url` only when it is an absolute http(s) URL, otherwise `undefined`.
 *
 * Source links come from web-search results the backend relays, so they are
 * untrusted: a `javascript:`/`data:` URL in an `href` would execute in the
 * app's origin when clicked.
 */
export function safeHttpUrl(url: string | null | undefined): string | undefined {
  if (!url) return undefined
  try {
    const parsed = new URL(url.trim())
    return parsed.protocol === 'https:' || parsed.protocol === 'http:' ? parsed.href : undefined
  } catch {
    return undefined
  }
}
