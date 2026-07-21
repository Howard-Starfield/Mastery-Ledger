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
})
