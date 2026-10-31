import "@fontsource-variable/manrope/index.css";
import "./styles.css";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import App from "./App";
import { applyPhotoFit, applyTheme } from "./theme";

applyTheme();
applyPhotoFit();

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: (count, err: unknown) => (err as { status?: number })?.status !== 401 && count < 2, staleTime: 15_000 } },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
