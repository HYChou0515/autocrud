import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './index.css';
import { applyCustomizations } from './generated/resources';
import { customizations } from './lib/resourceCustomization';
import App from './App';

applyCustomizations(customizations);

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
