import { Navigate, Route, Routes } from "react-router-dom";
import Shell from "./components/Shell";
import Builder from "./pages/Builder";
import Chat from "./pages/Chat";
import Dashboard from "./pages/Dashboard";
import Gallery from "./pages/Gallery";
import RunDetail from "./pages/RunDetail";
import StressTest from "./pages/StressTest";

export default function App() {
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route index element={<Gallery />} />
        <Route path="builder" element={<Builder />} />
        <Route path="builder/:id" element={<Builder />} />
        <Route path="chat/:id" element={<Chat />} />
        <Route path="dashboard" element={<Dashboard />} />
        <Route path="runs/:id" element={<RunDetail />} />
        <Route path="stress/:id" element={<StressTest />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
