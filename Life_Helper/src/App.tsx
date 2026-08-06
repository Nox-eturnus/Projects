import { PwaPrompts } from './pwa/PwaPrompts'
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

function App() {
  return (
    <RouterProvider>
      <AppShell>
        <Routes
          routes={[
            { path: '/', element: <TodayPlaceholder /> },
            { path: '/gallery', element: <GalleryRoute /> },
          ]}
          notFound={<p>Page not found.</p>}
        />
      </AppShell>
      <PwaPrompts />
    </RouterProvider>
  )
}

export default App
