import { useState } from "react";
import { setApiKey } from "../api.js";

export default function ApiKeyGate({ detail, onReady, onRetry }) {
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const submit = async (e) => {
    e.preventDefault();
    const trimmed = key.trim();
    if (!trimmed || busy) return;
    setBusy(true);
    setError(null);
    try {
      await setApiKey(trimmed);
      onReady();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="gate-overlay">
      <form className="gate-card" onSubmit={submit}>
        <div className="brand-logo">▲</div>
        <h2>Claude API anahtarınızı girin</h2>
        <p>
          PrintForge AI, tasarım ajanları için bir Claude API anahtarı kullanır. Anahtarınız sadece bu
          bilgisayardaki sunucuda tutulur; hiçbir üçüncü tarafa gönderilmez.
        </p>
        <input
          type="password"
          autoFocus
          value={key}
          onChange={(e) => setKey(e.target.value)}
          placeholder="sk-ant-..."
          disabled={busy}
        />
        {error && <div className="banner error gate-error">{error}</div>}
        <button className="primary-btn" type="submit" disabled={busy || !key.trim()}>
          {busy ? <span className="spinner small" /> : "Devam et"}
        </button>
        <a href="https://platform.claude.com/settings/keys" target="_blank" rel="noreferrer">
          Anahtarınız yok mu? platform.claude.com üzerinden oluşturun →
        </a>
        {detail && (
          <p className="gate-detail">
            {detail} Claude Code aboneliğinizle çalıştırmayı tercih ediyorsanız, Terminal'de giriş yaptıktan
            sonra{" "}
            <button type="button" className="link-btn" onClick={onRetry}>
              yeniden kontrol edin
            </button>
            .
          </p>
        )}
      </form>
    </div>
  );
}
