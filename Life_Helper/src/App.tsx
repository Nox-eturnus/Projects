import { useGlobalCaptureShortcut } from './capture/useGlobalCaptureShortcut'
import { PwaPrompts } from './pwa/PwaPrompts'
import { CaptureRoute } from './routes/CaptureRoute'
import { GalleryRoute } from './routes/GalleryRoute'
import { AppShell } from './ui/AppShell'
import { RouterProvider, Routes } from './ui/router'

function TodayPlaceholder() {
  return (
    <>
      <h1>Life Helper</h1>
      <p>Foundations are laid. Capture comes next.</p>
    </>
  )
}

function AppRoutes() {
  // Must be mounted under RouterProvider (it calls useRouter()), and above
  // any single route, so Ctrl/Cmd+K opens capture regardless of which route
  // is current — see docs/phase_B1_capture_surface.md.
  useGlobalCaptureShortcut()
  return (
    <Routes
      routes={[
        { path: '/', element: <TodayPlaceholder /> },
        { path: '/capture', element: <CaptureRoute /> },
        { path: '/gallery', element: <GalleryRoute /> },
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
