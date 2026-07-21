import { describe, expect, it } from 'vitest'

import { lessonDocument } from './StudyReader'

describe('lessonDocument', () => {
  it('renders markdown, preserves raw HTML, and blocks active content', () => {
    const document = lessonDocument(
      '# Feedback loops\n\n<aside><strong>Example</strong></aside>\n\n<script>window.parent.compromised = true</script>',
    )

    expect(document).toContain('<h1>Feedback loops</h1>')
    expect(document).toContain('<aside><strong>Example</strong></aside>')
    expect(document).toContain('<script>window.parent.compromised = true</script>')
    expect(document).toContain("script-src 'none'")
    expect(document).toContain("object-src 'none'")
    expect(document).toContain("form-action 'none'")
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
