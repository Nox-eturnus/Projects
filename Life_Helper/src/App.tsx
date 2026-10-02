import { useGlobalCaptureShortcut } from './capture/useGlobalCaptureShortcut'
import { useRecordOpens } from './gate/useGateRecorders'
import { PwaPrompts } from './pwa/PwaPrompts'
import { CaptureRoute } from './routes/CaptureRoute'
import { GalleryRoute } from './routes/GalleryRoute'
import { GateRoute } from './routes/GateRoute'
import { InboxRoute } from './routes/InboxRoute'
import { RevisitRoute } from './routes/RevisitRoute'
import { SettingsRoute } from './routes/SettingsRoute'
import { ShutdownRoute } from './routes/ShutdownRoute'
import { SomedayRoute } from './routes/SomedayRoute'
import { TodayRoute } from './routes/TodayRoute'
import { AppShell } from './ui/AppShell'
import { RouterProvider, Routes } from './ui/router'

function AppRoutes() {
  // Must be mounted under RouterProvider (it calls useRouter()), and above
  // any single route, so Ctrl/Cmd+K opens capture regardless of which route
  // is current — see docs/phase_B1_capture_surface.md.
  useGlobalCaptureShortcut()
  // Part C6: which days the app was opened, for the gate report.
  useRecordOpens()
  return (
    <Routes
      routes={[
        { path: '/', element: <TodayRoute /> },
        { path: '/shutdown', element: <ShutdownRoute /> },
        { path: '/capture', element: <CaptureRoute /> },
        { path: '/inbox', element: <InboxRoute /> },
        { path: '/revisit', element: <RevisitRoute /> },
        { path: '/someday', element: <SomedayRoute /> },
        { path: '/settings', element: <SettingsRoute /> },
        { path: '/gallery', element: <GalleryRoute /> },
        { path: '/gate', element: <GateRoute /> },
      ]}
      notFound={<p>Page not found.</p>}
    />
  )
}

function App() {
  return (
    <RouterProvider>
      <AppShell>
        <AppRoutes />
      </AppShell>
      <PwaPrompts />
    </RouterProvider>
  )
}

export default App
