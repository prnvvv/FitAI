/**
 * Prepares assistant text for the Markdown renderer.
 *
 * The assistant usually answers in Markdown, but it sometimes emits
 * presentational HTML — most often `<br>`, occasionally `<b>`, `<ul>` or a whole
 * `<table>` — inside otherwise valid Markdown. Raw HTML is deliberately never
 * rendered (the app does not enable `rehype-raw`), so those tags would show up
 * as literal text. This helper rewrites the small set of formatting tags the
 * assistant actually produces into their Markdown equivalents and drops any
 * other tag while keeping its inner text.
 *
 * Nothing unsafe can get through: the output is plain Markdown, unknown markup
 * is discarded rather than rendered, and every tag is stripped from the text.
 *
 * Code is never touched. Fenced blocks and inline code spans are copied
 * verbatim, so examples that talk about HTML keep their angle brackets.
 */

/** Two trailing spaces plus a newline: the CommonMark hard line break. */
const HARD_BREAK = '  \n'

/** A fence opener/closer: up to three leading spaces, then ``` or ~~~. */
const FENCE_MARKER = /^ {0,3}(?:```|~~~)/

/** An inline code span, captured so `split` keeps it at odd indices. */
const INLINE_CODE = /(`+[^`\n]*`+)/

/** Any remaining HTML-looking tag. */
const TAG = /<\/?[a-z][a-z0-9-]*(\s[^<>]*)?\/?>/gi

/** Tags that end a block; they become paragraph breaks. */
const BLOCK_TAGS = /<\/?(?:p|div|section|article|blockquote|pre|table|thead|tbody|tfoot|tr)\b[^>]*>/gi

/** Links are only rewritten when the href cannot execute script. */
const SAFE_HREF = /^(?:https?:|mailto:|\/)/i

/** Collapses the blank lines the conversions tend to leave behind. */
function tidy(text: string): string {
  return text.replace(/\n{3,}/g, '\n\n')
}

/** Converts the rows of a raw HTML table into a GFM table. */
function htmlTableToMarkdown(html: string): string {
  const rows = [...html.matchAll(/<tr\b[^>]*>([\s\S]*?)<\/tr\s*>/gi)]
    .map((row) =>
      [...row[1].matchAll(/<t[hd]\b[^>]*>([\s\S]*?)<\/t[hd]\s*>/gi)].map((cell) =>
        cell[1]
          .replace(/<br\s*\/?>/gi, ' ')
          .replace(/<[^>]*>/g, ' ')
          .replace(/\|/g, '\\|')
          .replace(/\s+/g, ' ')
          .trim(),
      ),
    )
    .filter((cells) => cells.length > 0)

  if (!rows.length) return ''

  const width = Math.max(...rows.map((cells) => cells.length))
  const row = (cells: string[]) =>
    `| ${[...cells, ...Array<string>(width - cells.length).fill('')].join(' | ')} |`

  return [
    row(rows[0]),
    `| ${Array<string>(width).fill('---').join(' | ')} |`,
    ...rows.slice(1).map(row),
  ].join('\n')
}

/** Turns `<ul>`/`<ol>` blocks into Markdown list items. */
function convertLists(text: string): string {
  return text.replace(
    /<(ul|ol)\b[^>]*>([\s\S]*?)<\/\1\s*>/gi,
    (_match, kind: string, inner: string) => {
      const marker = kind.toLowerCase() === 'ol' ? '1. ' : '- '
      const items = inner
        .split(/<li\b[^>]*>/i)
        .slice(1)
        .map((item) => item.replace(/<\/li\s*>/gi, '').trim())
        .filter(Boolean)
      if (!items.length) return '\n'
      return `\n\n${items.map((item) => `${marker}${item}`).join('\n')}\n\n`
    },
  )
}

/** Rewrites the supported HTML subset; strips everything else. */
function convertTags(text: string): string {
  const withBlocks = text
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(
      /<table\b[^>]*>([\s\S]*?)<\/table\s*>/gi,
      (_match, body: string) => `\n\n${htmlTableToMarkdown(body)}\n\n`,
    )

  return tidy(
    convertLists(withBlocks)
      .replace(
        /<a\b[^>]*href=["']([^"']+)["'][^>]*>([\s\S]*?)<\/a\s*>/gi,
        (_match, href: string, label: string) => {
          const text = label.replace(/<[^>]*>/g, '').trim()
          return SAFE_HREF.test(href) ? `[${text}](${href})` : text
        },
      )
      .replace(/<br\s*\/?>/gi, HARD_BREAK)
      .replace(/<(b|strong)\b[^>]*>([\s\S]*?)<\/\1\s*>/gi, '**$2**')
      .replace(/<(i|em)\b[^>]*>([\s\S]*?)<\/\1\s*>/gi, '*$2*')
      .replace(/<code\b[^>]*>([\s\S]*?)<\/code\s*>/gi, '`$1`')
      .replace(
        /<h([1-6])\b[^>]*>([\s\S]*?)<\/h\1\s*>/gi,
        (_match, level: string, inner: string) =>
          `\n\n${'#'.repeat(Number(level))} ${inner.trim()}\n\n`,
      )
      .replace(/<hr\s*\/?>/gi, '\n\n---\n\n')
      .replace(BLOCK_TAGS, '\n\n')
      .replace(/<li\b[^>]*>/gi, '\n- ')
      .replace(TAG, ''),
  )
}

/** Applies `transform` to prose only, leaving inline code spans alone. */
function mapProse(text: string, transform: (prose: string) => string): string {
  return text
    .split(INLINE_CODE)
    .map((part, index) => (index % 2 === 1 ? part : transform(part)))
    .join('')
}

/** Applies `transform` to everything outside fenced code blocks. */
function mapCodeBlocks(content: string, transform: (prose: string) => string): string {
  const out: string[] = []
  let pending: string[] = []
  let inFence = false

  const flush = () => {
    if (!pending.length) return
    const chunk = pending.join('\n')
    out.push(inFence ? chunk : transform(chunk))
    pending = []
  }

  for (const line of content.split('\n')) {
    if (FENCE_MARKER.test(line)) {
      flush()
      inFence = !inFence
    }
    pending.push(line)
  }
  flush()

  return out.join('\n')
}

/**
 * Normalises assistant Markdown for rendering. Content without a `<` is
 * returned untouched, which keeps ordinary responses on the fast path.
 */
export function normalizeMarkdown(content: string): string {
  if (!content.includes('<')) return content
  // Prose chunks are converted in place, so only the whole message is trimmed:
  // trimming per chunk would eat the spaces around inline code spans.
  return mapCodeBlocks(content, (prose) => mapProse(prose, convertTags)).trim()
}
