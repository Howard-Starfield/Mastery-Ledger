import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import App from './App'
import { AppearanceProvider } from './AppearanceProvider'
import UpdateNotice from './UpdateNotice'
import './styles/globals.css'
import './styles.css'
import './styles/workbench.css'
import './styles/update.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AppearanceProvider>
      <App />
      <UpdateNotice />
    </AppearanceProvider>
  </StrictMode>,
)
