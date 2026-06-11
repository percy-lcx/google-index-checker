import { BrowserRouter, Routes, Route, Link } from "react-router-dom";
import NewCheck from "./pages/NewCheck";
import CheckResult from "./pages/CheckResult";
import CheckHistory from "./pages/CheckHistory";
import UrlDetail from "./pages/UrlDetail";
import Properties from "./pages/Properties";
import Watchlist from "./pages/Watchlist";
import Schedule from "./pages/Schedule";
import "./App.css";

function App() {
  return (
    <BrowserRouter>
      <div className="app">
        <header className="app-header">
          <Link to="/" className="logo">GSC Indexation Checker</Link>
          <nav>
            <Link to="/">Check URLs</Link>
            <Link to="/history">History</Link>
            <Link to="/watchlist">Watchlist</Link>
            <Link to="/schedule">Schedule</Link>
            <Link to="/properties">Properties</Link>
          </nav>
        </header>
        <main className="app-main">
          <Routes>
            <Route path="/" element={<NewCheck />} />
            <Route path="/checks/:id" element={<CheckResult />} />
            <Route path="/history" element={<CheckHistory />} />
            <Route path="/watchlist" element={<Watchlist />} />
            <Route path="/schedule" element={<Schedule />} />
            <Route path="/urls/:urlString" element={<UrlDetail />} />
            <Route path="/properties" element={<Properties />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}

export default App;
