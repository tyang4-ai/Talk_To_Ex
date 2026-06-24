import { Navigate, useLocation } from "react-router-dom";
import type { ReactNode } from "react";
import { isAuthed } from "../api/client";

/** Gate wizard/dashboard routes behind a JWT; bounce to /auth otherwise. */
export default function ProtectedRoute({ children }: { children: ReactNode }) {
  const location = useLocation();
  if (!isAuthed()) {
    return <Navigate to="/auth" replace state={{ from: location.pathname }} />;
  }
  return <>{children}</>;
}
