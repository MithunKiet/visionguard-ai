import { Navigate, createBrowserRouter, useLocation } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { ChangePassword } from "./pages/ChangePassword";
import { Login } from "./pages/Login";
import { Dashboard } from "./pages/Dashboard";
import { Cameras } from "./pages/Cameras";
import { LiveGrid } from "./pages/LiveGrid";
import { Alerts } from "./pages/Alerts";
import { NotificationDeliveries } from "./pages/NotificationDeliveries";
import { Violations } from "./pages/Violations";
import { Enterprises } from "./pages/Enterprises";
import { Factories } from "./pages/Factories";
import { Departments } from "./pages/Departments";
import { Zones } from "./pages/Zones";
import { Users } from "./pages/Users";
import { useAuthStore } from "./store/authStore";
import { LiveFeedProvider } from "./hooks/useWebSocket";

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const accessToken = useAuthStore((s) => s.accessToken);
  const user = useAuthStore((s) => s.user);
  const location = useLocation();
  if (!accessToken) return <Navigate to="/login" replace />;
  if (user?.is_first_login && location.pathname !== "/change-password") return <Navigate to="/change-password" replace />;
  return <>{children}</>;
}

export const router = createBrowserRouter([
  { path: "/login", element: <Login /> },
  { path: "/change-password", element: <ProtectedRoute><ChangePassword /></ProtectedRoute> },
  {
    path: "/",
    element: (
      <ProtectedRoute>
        <LiveFeedProvider><AppShell /></LiveFeedProvider>
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
      { path: "notification-deliveries", element: <NotificationDeliveries /> },
    ],
  },
]);
