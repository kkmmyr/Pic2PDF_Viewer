import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/Layout';
import GeneratorPage from './pages/GeneratorPage';
import ViewerPage from './pages/ViewerPage';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Navigate to="/viewer" replace />} />
          <Route path="viewer" element={<ViewerPage />} />
          <Route path="generator" element={<GeneratorPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
