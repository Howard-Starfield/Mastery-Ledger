import type { AppearanceSettings, ThemeMode } from '@/api'

export type ResolvedTheme = 'light' | 'dark'

export const DEFAULT_APPEARANCE: AppearanceSettings = {
  schema_version: 'appearance-settings-v1',
  theme_mode: 'system',
  navigation_panel_open: true,
  navigation_panel_width: 224,
  ui_scale: 100,
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
  return Math.min(332, Math.max(224, Math.round(width)))
}

export const UI_SCALE_OPTIONS = [80, 90, 100, 110, 125] as const

export function normalizeUiScale(scale: number): number {
  return UI_SCALE_OPTIONS.reduce((closest, candidate) =>
    Math.abs(candidate - scale) < Math.abs(closest - scale) ? candidate : closest,
  )
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

export function applyUiScale(scale: number): void {
  document.documentElement.style.setProperty('zoom', String(normalizeUiScale(scale) / 100))
}
