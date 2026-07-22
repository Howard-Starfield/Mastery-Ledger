import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import App from './App'
import { AppearanceProvider } from './AppearanceProvider'
import './styles/globals.css'
import './styles.css'
import './styles/workbench.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AppearanceProvider>
      <App />
    </AppearanceProvider>
  </StrictMode>,
)
