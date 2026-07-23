import { describe, expect, it } from 'vitest'

import { lessonDocument } from './StudyReader'

describe('lessonDocument', () => {
  it('renders markdown, preserves raw HTML, and blocks active content', () => {
    const document = lessonDocument(
      '# Feedback loops\n\n<aside><strong>Example</strong></aside>\n\n<script>window.parent.compromised = true</script>',
    )

    expect(document).toContain('<h1>Feedback loops</h1>')
    expect(document).toContain('<main class="lesson-note">')
    expect(document).toContain('min-height: 100vh')
    expect(document).toContain('background: #ffffff')
    expect(document).toContain('width: min(720px, 100%)')
    expect(document).toContain('font-size: 16px')
    expect(document).toContain('line-height: 1.7')
    expect(document).toContain('scrollbar-color: #9aa3b1 transparent')
    expect(document).toContain('linear-gradient(90deg, #7b8492, #9aa3b1 42%, #d6dbe3 58%, #9aa3b1)')
    expect(document).toContain('<aside><strong>Example</strong></aside>')
    expect(document).toContain('<script>window.parent.compromised = true</script>')
    expect(document).toContain("script-src 'none'")
    expect(document).toContain("object-src 'none'")
    expect(document).toContain("form-action 'none'")
  })

  it('renders the exact dark reading palette when the shell is dark', () => {
    const document = lessonDocument('# Dark reading', 'dark')

    expect(document).toContain('<html lang="en" data-theme="dark">')
    expect(document).toContain('background: #1e1e1e')
    expect(document).toContain('color: #c9cacb')
    expect(document).toContain('background: #0d263e')
    expect(document).toContain('color: #6aaeff')
    expect(document).toContain('scrollbar-color: #777a80 transparent')
    expect(document).toContain('linear-gradient(90deg, #55585e, #777a80 42%, #a8abb1 58%, #777a80)')
  })

  it('renders lesson source references as linked footnotes instead of Markdown syntax', () => {
    const document = lessonDocument(
      '# Grounded lesson\n\nA supported statement.[^REF-001]\n\n## Sources used\n\n[^REF-001]: [SRC-001] 00:01:10-00:01:20.',
    )

    expect(document).toContain('data-footnote-ref')
    expect(document).toContain('href="#footnote-REF-001"')
    expect(document).toContain('data-footnotes')
    expect(document).not.toContain('[^REF-001]')
  })
})
