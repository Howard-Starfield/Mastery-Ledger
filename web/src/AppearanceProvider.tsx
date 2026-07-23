import {
  createContext,
  type PropsWithChildren,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'

import {
  applicationApi,
  type AppearanceSettings,
  type AppearanceSettingsUpdate,
} from '@/api'
import {
  applyResolvedTheme,
  applyUiScale,
  clampNavigationPanelWidth,
  DEFAULT_APPEARANCE,
  normalizeUiScale,
  resolveTheme,
  type ResolvedTheme,
} from '@/lib/appearance'

type AppearanceContextValue = {
  settings: AppearanceSettings
  resolvedTheme: ResolvedTheme
  error: string | null
  updateAppearance: (patch: Partial<AppearanceSettingsUpdate>) => Promise<void>
}

const AppearanceContext = createContext<AppearanceContextValue | null>(null)

function systemPrefersDark(): boolean {
  return window.matchMedia('(prefers-color-scheme: dark)').matches
}

export function AppearanceProvider({ children }: PropsWithChildren) {
  const [settings, setSettings] = useState(DEFAULT_APPEARANCE)
  const [resolvedTheme, setResolvedTheme] = useState<ResolvedTheme>(() =>
    resolveTheme(DEFAULT_APPEARANCE.theme_mode, systemPrefersDark()),
  )
  const [error, setError] = useState<string | null>(null)
  const settingsRef = useRef(settings)

  const commitLocalSettings = useCallback((next: AppearanceSettings) => {
    settingsRef.current = next
    setSettings(next)
  }, [])

  useEffect(() => {
    let cancelled = false
    applicationApi
      .appearanceSettings()
      .then((saved) => {
        if (!cancelled) {
          commitLocalSettings({
            ...saved,
            navigation_panel_width: clampNavigationPanelWidth(saved.navigation_panel_width),
            ui_scale: normalizeUiScale(saved.ui_scale ?? DEFAULT_APPEARANCE.ui_scale),
          })
        }
      })
      .catch(() => {
        // Appearance failure must not prevent onboarding or workspace recovery.
      })
    return () => {
      cancelled = true
    }
  }, [commitLocalSettings])

  useEffect(() => {
    const media = window.matchMedia('(prefers-color-scheme: dark)')
    const apply = () => {
      const nextResolved = resolveTheme(settings.theme_mode, media.matches)
      setResolvedTheme(nextResolved)
      applyResolvedTheme(nextResolved, settings.theme_mode)
    }
    apply()
    media.addEventListener('change', apply)
    return () => media.removeEventListener('change', apply)
  }, [settings.theme_mode])

  useEffect(() => {
    applyUiScale(settings.ui_scale)
  }, [settings.ui_scale])

  const updateAppearance = useCallback(
    async (patch: Partial<AppearanceSettingsUpdate>) => {
      const previous = settingsRef.current
      const next: AppearanceSettings = {
        ...previous,
        ...patch,
        navigation_panel_width: clampNavigationPanelWidth(
          patch.navigation_panel_width ?? previous.navigation_panel_width,
        ),
        ui_scale: normalizeUiScale(patch.ui_scale ?? previous.ui_scale),
      }
      commitLocalSettings(next)
      setError(null)
      try {
        const saved = await applicationApi.updateAppearanceSettings({
          theme_mode: next.theme_mode,
          navigation_panel_open: next.navigation_panel_open,
          navigation_panel_width: next.navigation_panel_width,
          ui_scale: next.ui_scale,
          content_theme: next.content_theme,
        })
        commitLocalSettings(saved)
      } catch (cause) {
        if (settingsRef.current === next) commitLocalSettings(previous)
        setError(cause instanceof Error ? cause.message : 'Appearance settings could not be saved.')
        throw cause
      }
    },
    [commitLocalSettings],
  )

  const value = useMemo(
    () => ({ settings, resolvedTheme, error, updateAppearance }),
    [settings, resolvedTheme, error, updateAppearance],
  )

  return <AppearanceContext.Provider value={value}>{children}</AppearanceContext.Provider>
}

export function useAppearance(): AppearanceContextValue {
  const value = useContext(AppearanceContext)
  if (!value) throw new Error('useAppearance must be used inside AppearanceProvider.')
  return value
}
