import { useState } from "react";
import { Routes, Route } from "react-router-dom";
import Layout from "@/components/Layout";
import Dashboard from "@/pages/Dashboard";
import Servers from "@/pages/Servers";
import ServerDetail from "@/pages/ServerDetail";
import Apps from "@/pages/Apps";
import AppDetail from "@/pages/AppDetail";
import Databases from "@/pages/Databases";
import Login from "@/pages/Login";
import { getApiKey, clearApiKey } from "@/api/client";

export default function App() {
  const [authenticated, setAuthenticated] = useState(!!getApiKey());

  if (!authenticated) {
    return <Login onLogin={() => setAuthenticated(true)} />;
  }

  return (
    <Routes>
      <Route
        element={
          <Layout
            onLogout={() => {
              clearApiKey();
              setAuthenticated(false);
            }}
          />
        }
      >
        <Route index element={<Dashboard />} />
        <Route path="servers" element={<Servers />} />
        <Route path="servers/:name" element={<ServerDetail />} />
        <Route path="apps" element={<Apps />} />
        <Route path="apps/:name" element={<AppDetail />} />
        <Route path="databases" element={<Databases />} />
        {/* Catch-all redirect to dashboard */}
        <Route path="*" element={<Dashboard />} />
      </Route>
    </Routes>
  );
}
