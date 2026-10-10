import { useEffect, useState } from "react";

const API = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export default function App() {
  const [health, setHealth] = useState("проверка…");

  useEffect(() => {
    fetch(`${API}/health`)
      .then((r) => r.json())
      .then((d) => setHealth(d.status === "ok" ? "доступен" : "ошибка"))
      .catch(() => setHealth("недоступен"));
  }, []);

  return (
    <main style={{ fontFamily: "system-ui, sans-serif", padding: "2rem" }}>
      <h1>ComplianceRadar</h1>
      <p>Мониторинг сайтов банков на возможные несоответствия требованиям ЦБ.</p>
      <p>Backend: {health}</p>
    </main>
  );
}
