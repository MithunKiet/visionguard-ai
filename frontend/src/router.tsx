import { Navigate, createBrowserRouter } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { Login } from "./pages/Login";
import { Dashboard } from "./pages/Dashboard";
import { Cameras } from "./pages/Cameras";
import { LiveGrid } from "./pages/LiveGrid";
import { Alerts } from "./pages/Alerts";
import { Violations } from "./pages/Violations";
import { Enterprises } from "./pages/Enterprises";
import { Factories } from "./pages/Factories";
import { Departments } from "./pages/Departments";
import { Zones } from "./pages/Zones";
import { Users } from "./pages/Users";
import { useAuthStore } from "./store/authStore";

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const accessToken = useAuthStore((s) => s.accessToken);
  if (!accessToken) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export const router = createBrowserRouter([
  { path: "/login", element: <Login /> },
  {
    path: "/",
    element: (
      <ProtectedRoute>
        <AppShell />
      </ProtectedRoute>
    ),
    children: [
      { index: true, element: <Dashboard /> },
      { path: "enterprises", element: <Enterprises /> },
      { path: "factories", element: <Factories /> },
      { path: "departments", element: <Departments /> },
      { path: "zones", element: <Zones /> },
      { path: "cameras", element: <Cameras /> },
      { path: "users", element: <Users /> },
      { path: "live", element: <LiveGrid /> },
      { path: "violations", element: <Violations /> },
      { path: "alerts", element: <Alerts /> },
    ],
  },
]);
