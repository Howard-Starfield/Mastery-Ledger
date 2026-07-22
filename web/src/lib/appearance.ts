import type { AppearanceSettings, ThemeMode } from '@/api'

export type ResolvedTheme = 'light' | 'dark'

export const DEFAULT_APPEARANCE: AppearanceSettings = {
  schema_version: 'appearance-settings-v1',
  theme_mode: 'system',
  navigation_panel_open: true,
  navigation_panel_width: 312,
  content_theme: 'infield',
}

export function resolveTheme(mode: ThemeMode, systemPrefersDark: boolean): ResolvedTheme {
  if (mode === 'system') return systemPrefersDark ? 'dark' : 'light'
  return mode
}

export function nextThemeMode(mode: ThemeMode): ThemeMode {
  if (mode === 'system') return 'light'
  if (mode === 'light') return 'dark'
  return 'system'
}

export function clampNavigationPanelWidth(width: number): number {
  return Math.min(432, Math.max(300, Math.round(width)))
}

export function shouldAutoCollapseNavigation(viewportWidth: number): boolean {
  return viewportWidth < 820
}

export function applyResolvedTheme(theme: ResolvedTheme, mode: ThemeMode): void {
  const root = document.documentElement
  root.classList.toggle('dark', theme === 'dark')
  root.dataset.theme = theme
  root.dataset.themeMode = mode
}
