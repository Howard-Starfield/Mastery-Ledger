import { describe, expect, it } from 'vitest'

import {
  clampNavigationPanelWidth,
  nextThemeMode,
  resolveTheme,
  shouldAutoCollapseNavigation,
} from './appearance'

describe('appearance helpers', () => {
  it('resolves explicit and operating-system themes', () => {
    expect(resolveTheme('light', true)).toBe('light')
    expect(resolveTheme('dark', false)).toBe('dark')
    expect(resolveTheme('system', false)).toBe('light')
    expect(resolveTheme('system', true)).toBe('dark')
  })

  it('rounds and clamps persisted navigation widths', () => {
    expect(clampNavigationPanelWidth(219)).toBe(300)
    expect(clampNavigationPanelWidth(299.6)).toBe(300)
    expect(clampNavigationPanelWidth(500)).toBe(432)
  })

  it('uses compact navigation only when the window cannot support both panes', () => {
    expect(shouldAutoCollapseNavigation(819)).toBe(true)
    expect(shouldAutoCollapseNavigation(820)).toBe(false)
  })

  it('rotates through the three theme modes', () => {
    expect(nextThemeMode('system')).toBe('light')
    expect(nextThemeMode('light')).toBe('dark')
    expect(nextThemeMode('dark')).toBe('system')
  })
})
