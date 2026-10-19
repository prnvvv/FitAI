import { describe, expect, it } from 'vitest'
import { normalizeMarkdown } from './markdown'

describe('normalizeMarkdown', () => {
  it('leaves ordinary markdown untouched', () => {
    const markdown = '# Title\n\nText with **bold**, `code` and a list.\n\n- one\n- two'
    expect(normalizeMarkdown(markdown)).toBe(markdown)
  })

  it('turns <br> into a hard line break', () => {
    const out = normalizeMarkdown('Warm up 5 min<br>Then 3 sets')
    expect(out).toBe('Warm up 5 min  \nThen 3 sets')
    expect(out).not.toContain('<br>')
  })

  it('handles self-closing and uppercase break tags', () => {
    expect(normalizeMarkdown('a<br/>b')).toBe('a  \nb')
    expect(normalizeMarkdown('a<BR />b')).toBe('a  \nb')
  })

  it('keeps <br> inside fenced code blocks', () => {
    const markdown = 'Example:\n\n```html\nLine one<br>Line two\n```\n\nDone'
    expect(normalizeMarkdown(markdown)).toBe(markdown)
  })

  it('keeps <br> inside inline code', () => {
    expect(normalizeMarkdown('Use `<br>` for a break')).toBe('Use `<br>` for a break')
  })

  it('converts emphasis and strong tags', () => {
    expect(normalizeMarkdown('<b>Sets</b>: <i>3x10</i>')).toBe('**Sets**: *3x10*')
    expect(normalizeMarkdown('<strong>Heavy</strong> <em>light</em>')).toBe('**Heavy** *light*')
  })

  it('converts headings and rules', () => {
    expect(normalizeMarkdown('<h3>Day 1</h3>')).toBe('### Day 1')
    expect(normalizeMarkdown('above<hr>below')).toBe('above\n\n---\n\nbelow')
  })

  it('converts unordered and ordered lists', () => {
    expect(normalizeMarkdown('<ul><li>Squat</li><li>Bench</li></ul>')).toBe(
      '- Squat\n- Bench',
    )
    expect(normalizeMarkdown('<ol><li>Warm up</li><li>Work sets</li></ol>')).toBe(
      '1. Warm up\n1. Work sets',
    )
  })

  it('converts a raw HTML table into a markdown table', () => {
    const html =
      '<table><thead><tr><th>Day</th><th>Exercise</th></tr></thead>' +
      '<tbody><tr><td>Mon</td><td>Squat<br>3x5</td></tr><tr><td>Wed</td><td>Bench</td></tr></tbody></table>'
    expect(normalizeMarkdown(html)).toBe(
      '| Day | Exercise |\n| --- | --- |\n| Mon | Squat 3x5 |\n| Wed | Bench |',
    )
  })

  it('escapes pipes inside table cells', () => {
    const html = '<table><tr><td>A | B</td><td>C</td></tr><tr><td>D</td><td>E</td></tr></table>'
    expect(normalizeMarkdown(html)).toContain('| A \\| B | C |')
  })

  it('strips unsupported tags but keeps their text', () => {
    expect(normalizeMarkdown('<span class="x">Readable</span> text')).toBe('Readable text')
    expect(normalizeMarkdown('Before <script>alert(1)</script> after')).toBe(
      'Before alert(1) after',
    )
  })

  it('turns paragraphs into separate blocks', () => {
    expect(normalizeMarkdown('<p>One</p><p>Two</p>')).toBe('One\n\nTwo')
  })

  it('converts safe links and drops unsafe hrefs', () => {
    expect(normalizeMarkdown('<a href="https://example.com">Guide</a>')).toBe(
      '[Guide](https://example.com)',
    )
    expect(normalizeMarkdown('<a href="javascript:alert(1)">Click</a>')).toBe('Click')
  })

  it('drops html comments and never leaves triple blank lines', () => {
    const out = normalizeMarkdown('One\n\n<!-- note -->\n\n<p>Two</p>\n\n\nThree')
    expect(out).not.toContain('<!--')
    expect(out).not.toMatch(/\n{3,}/)
  })

  it('keeps a workout response readable', () => {
    const out = normalizeMarkdown(
      '<h3>Push Day</h3><ul><li>Bench 4x6<br>2 min rest</li><li>Fly 3x12</li></ul>' +
        '<p>Finish with 10 min easy cardio.</p>',
    )
    expect(out).toContain('### Push Day')
    expect(out).toContain('- Bench 4x6  \n2 min rest')
    expect(out).toContain('- Fly 3x12')
    expect(out).toContain('Finish with 10 min easy cardio.')
    expect(out).not.toMatch(/<\/?[a-z]/i)
  })
})
