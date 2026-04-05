import { BrowserRouter, Routes, Route, Link } from "react-router-dom";
import NewCheck from "./pages/NewCheck";
import CheckResult from "./pages/CheckResult";
import CheckHistory from "./pages/CheckHistory";
import UrlDetail from "./pages/UrlDetail";
import "./App.css";

function App() {
  return (
    <BrowserRouter>
      <div className="app">
        <header className="app-header">
          <Link to="/" className="logo">GSC Indexation Checker</Link>
          <nav>
            <Link to="/">New Check</Link>
            <Link to="/history">History</Link>
          </nav>
        </header>
        <main className="app-main">
          <Routes>
            <Route path="/" element={<NewCheck />} />
            <Route path="/checks/:id" element={<CheckResult />} />
            <Route path="/history" element={<CheckHistory />} />
            <Route path="/urls/:urlString" element={<UrlDetail />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}

export default App;
