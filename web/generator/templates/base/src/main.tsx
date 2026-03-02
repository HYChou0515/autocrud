import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './index.css';
import { applyCustomizations } from './autocrud/generated/resources';
import { customizations } from './autocrud/lib/resourceCustomization';
import App from './App';

applyCustomizations(customizations);

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
