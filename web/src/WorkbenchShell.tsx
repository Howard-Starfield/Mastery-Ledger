import type { PropsWithChildren, ReactNode } from 'react'
import { useEffect, useRef, useState } from 'react'
import {
  BookOpen,
  BookText,
  FileCheck2,
  FolderSync,
  Monitor,
  Moon,
  PanelLeftClose,
  PanelLeftOpen,
  RefreshCw,
  RotateCcw,
  Settings2,
  Sun,
} from 'lucide-react'
import { Group, Panel, Separator, usePanelRef } from 'react-resizable-panels'

import { useAppearance } from '@/AppearanceProvider'
import type { ThemeMode } from '@/api'
import {
  clampNavigationPanelWidth,
  nextThemeMode,
  shouldAutoCollapseNavigation,
} from '@/lib/appearance'

export type WorkbenchDestination = 'study' | 'glossary' | 'exams'

type WorkbenchShellProps = PropsWithChildren<{
  activeDestination: WorkbenchDestination
  dueCount: number
  loading: boolean
  workspaceName: string
  workspacePath?: string
  contextContent?: ReactNode
  onNavigate: (destination: WorkbenchDestination) => void
  onStartReview: () => void
  onOpenSettings: () => void
  onChangeWorkspace: () => void
  onRescan: () => void
}>

const activityItems = [
  { destination: 'study' as const, label: 'Study', icon: BookOpen },
  { destination: 'glossary' as const, label: 'Glossary', icon: BookText },
  { destination: 'exams' as const, label: 'Exams', icon: FileCheck2 },
]

const destinationDescriptions: Record<WorkbenchDestination, string> = {
  study: 'Published lessons and course chapters',
  glossary: 'Definitions across your local courses',
  exams: 'Verified exams and self-checked practice',
}

const themeItems: Record<ThemeMode, { label: string; icon: typeof Monitor }> = {
  system: { label: 'System', icon: Monitor },
  light: { label: 'Light', icon: Sun },
  dark: { label: 'Dark', icon: Moon },
}

export default function WorkbenchShell({
  activeDestination,
  children,
  dueCount,
  loading,
  workspaceName,
  workspacePath,
  contextContent,
  onNavigate,
  onStartReview,
  onOpenSettings,
  onChangeWorkspace,
  onRescan,
}: WorkbenchShellProps) {
  const { settings, error: appearanceError, updateAppearance } = useAppearance()
  const panelRef = usePanelRef()
  const lastPanelWidth = useRef(48 + settings.navigation_panel_width)
  const manualCompactOpen = useRef(false)
  const [autoCollapsed, setAutoCollapsed] = useState(() =>
    shouldAutoCollapseNavigation(window.innerWidth),
  )

  useEffect(() => {
    const syncNavigationLayout = () => {
      const panel = panelRef.current
      if (!panel) return
      const compact = shouldAutoCollapseNavigation(window.innerWidth)
      if (compact && !manualCompactOpen.current) {
        setAutoCollapsed(true)
        panel.collapse()
        return
      }
      if (!compact) {
        manualCompactOpen.current = false
        setAutoCollapsed(false)
      }
      if (settings.navigation_panel_open) {
        panel.resize(`${48 + settings.navigation_panel_width}px`)
      } else {
        panel.collapse()
      }
    }
    syncNavigationLayout()
    window.addEventListener('resize', syncNavigationLayout)
    return () => window.removeEventListener('resize', syncNavigationLayout)
  }, [panelRef, settings.navigation_panel_open, settings.navigation_panel_width])

  const saveAppearance = (patch: Parameters<typeof updateAppearance>[0]) => {
    void updateAppearance(patch).catch(() => undefined)
  }

  const currentTheme = themeItems[settings.theme_mode]
  const nextTheme = nextThemeMode(settings.theme_mode)
  const ThemeIcon = currentTheme.icon
  const navigationPanelVisible = settings.navigation_panel_open && !autoCollapsed

  const toggleNavigationPanel = () => {
    const nextOpen = !navigationPanelVisible
    if (nextOpen) {
      manualCompactOpen.current = shouldAutoCollapseNavigation(window.innerWidth)
      setAutoCollapsed(false)
      panelRef.current?.expand()
    } else {
      manualCompactOpen.current = false
      panelRef.current?.collapse()
    }
    saveAppearance({ navigation_panel_open: nextOpen })
  }

  return (
    <div className="workbench-shell">
      <header className="workbench-topbar">
        <div className="workbench-brand" aria-label="Mastery Ledger">
          <span>ML</span>
        </div>
        <button
          type="button"
          className="workbench-icon-button"
          onClick={toggleNavigationPanel}
          aria-label={navigationPanelVisible ? 'Collapse navigation panel' : 'Expand navigation panel'}
          title={navigationPanelVisible ? 'Collapse navigation panel' : 'Expand navigation panel'}
        >
          {navigationPanelVisible ? <PanelLeftClose /> : <PanelLeftOpen />}
        </button>
        <div className="workbench-breadcrumb">
          <span>{workspaceName}</span>
          <b>/</b>
          <strong>{activityItems.find((item) => item.destination === activeDestination)?.label}</strong>
        </div>
        <button className="workbench-rescan" type="button" onClick={onRescan} disabled={loading}>
          <RefreshCw className={loading ? 'is-spinning' : ''} />
          <span>{loading ? 'Scanning' : 'Rescan'}</span>
        </button>
      </header>

      <div className="workbench-body">
        <Group
          id="mastery-ledger-workbench"
          orientation="horizontal"
          className="workbench-panels"
          onLayoutChanged={(_layout, meta) => {
            if (!meta.isUserInteraction) return
            const pixels = lastPanelWidth.current
            if (pixels <= 49) {
              saveAppearance({ navigation_panel_open: false })
              return
            }
            saveAppearance({
              navigation_panel_open: true,
              navigation_panel_width: clampNavigationPanelWidth(pixels - 48),
            })
          }}
        >
          <Panel
            id="navigation"
            panelRef={panelRef}
            defaultSize={`${48 + settings.navigation_panel_width}px`}
            minSize="272px"
            maxSize="380px"
            collapsedSize="48px"
            collapsible
            groupResizeBehavior="preserve-pixel-size"
            onResize={(size) => {
              lastPanelWidth.current = size.inPixels
              if (size.inPixels > 49 && autoCollapsed) {
                manualCompactOpen.current = true
                setAutoCollapsed(false)
              }
            }}
          >
            <div className="workbench-navigation">
              <aside className="activity-rail" aria-label="Primary navigation">
                <nav>
                  {activityItems.map(({ destination, label, icon: ActivityIcon }) => (
                    <button
                      key={destination}
                      type="button"
                      className={activeDestination === destination ? 'is-active' : ''}
                      aria-current={activeDestination === destination ? 'page' : undefined}
                      aria-label={label}
                      title={label}
                      onClick={() => onNavigate(destination)}
                    >
                      <ActivityIcon />
                    </button>
                  ))}
                  <button
                    type="button"
                    className="activity-review"
                    aria-label={dueCount ? `Review, ${dueCount} questions due` : 'Review, nothing due'}
                    title={dueCount ? `${dueCount} questions due` : 'Nothing due'}
                    onClick={onStartReview}
                    disabled={!dueCount}
                  >
                    <RotateCcw />
                    {Boolean(dueCount) && <span>{dueCount > 99 ? '99+' : dueCount}</span>}
                  </button>
                </nav>
                <div className="activity-rail__footer">
                  <button
                    type="button"
                    className="activity-theme"
                    aria-label={`Theme: ${currentTheme.label}. Switch to ${themeItems[nextTheme].label}`}
                    title={`${currentTheme.label} theme · switch to ${themeItems[nextTheme].label}`}
                    onClick={() => saveAppearance({ theme_mode: nextTheme })}
                  >
                    <ThemeIcon />
                    <span className="activity-theme__mode" aria-hidden="true">{currentTheme.label.slice(0, 1)}</span>
                  </button>
                  <button
                    type="button"
                    aria-label="Settings"
                    title="Settings"
                    onClick={onOpenSettings}
                  >
                    <Settings2 />
                  </button>
                  {appearanceError && <span className="appearance-error" role="status">{appearanceError}</span>}
                </div>
              </aside>

              <aside className="context-panel" aria-label="Workspace navigation">
                <header>
                  <div>
                    <strong title={workspaceName}>{workspaceName}</strong>
                    <span title={workspacePath}>{workspacePath || 'Local workspace'}</span>
                  </div>
                  <button
                    type="button"
                    onClick={onChangeWorkspace}
                    aria-label="Change workspace"
                    title="Change workspace"
                  >
                    <FolderSync />
                  </button>
                </header>
                <div className="context-panel__content">
                  {contextContent ?? (
                    <section className="context-current">
                      <p>Current view</p>
                      <strong>{activityItems.find((item) => item.destination === activeDestination)?.label}</strong>
                      <span>{destinationDescriptions[activeDestination]}</span>
                    </section>
                  )}
                </div>
              </aside>
            </div>
          </Panel>

          <Separator
            className="workbench-resize-handle"
            aria-label="Drag to resize navigation panel"
            title="Drag to resize navigation panel"
          >
            <span />
          </Separator>

          <Panel id="content" minSize="420px">
            {children}
          </Panel>
        </Group>
      </div>
    </div>
  )
}
