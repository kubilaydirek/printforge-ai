import { useEffect, useRef, useState } from "react";
import AgentTracker from "./AgentTracker.jsx";

const EXAMPLES = [
  "Masama kulaklık tutucu yap",
  "Telefon standı: 65° eğimli, şarj kablosu için alttan delik",
  "3 bölmeli kalemlik, toplam genişlik 100 mm",
  "Duvara vidalanan 4 kancalı anahtar askısı",
];

const MAX_IMAGES = 4;
const ACCEPTED_TYPES = ["image/png", "image/jpeg", "image/webp"];

export default function ChatPanel({ messages, jobs, busy, hasModel, onSend, onNewDesign, onOpenImage, health, healthError }) {
  const [text, setText] = useState("");
  const [attachments, setAttachments] = useState([]); // [{file, url}]
  const scrollRef = useRef(null);
  const fileInputRef = useRef(null);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, jobs]);

  useEffect(() => () => attachments.forEach((a) => URL.revokeObjectURL(a.url)), []); // eslint-disable-line react-hooks/exhaustive-deps

  const addFiles = (fileList) => {
    const incoming = Array.from(fileList).filter((f) => ACCEPTED_TYPES.includes(f.type));
    if (!incoming.length) return;
    setAttachments((prev) => [...prev, ...incoming.map((file) => ({ file, url: URL.createObjectURL(file) }))].slice(0, MAX_IMAGES));
  };

  const removeAttachment = (url) => {
    setAttachments((prev) => {
      const target = prev.find((a) => a.url === url);
      if (target) URL.revokeObjectURL(target.url);
      return prev.filter((a) => a.url !== url);
    });
  };

  const submit = (value = text) => {
    const v = value.trim();
    if ((!v && attachments.length === 0) || busy) return;
    onSend(v, attachments.map((a) => a.file));
    setText("");
    setAttachments([]);
  };

  const onPaste = (e) => {
    const files = Array.from(e.clipboardData?.files || []);
    if (files.length) addFiles(files);
  };

  return (
    <aside className="chat">
      <header className="chat-header">
        <div className="brand">
          <div className="brand-logo">▲</div>
          <div>
            <h1>PrintForge AI</h1>
            <p>
              Text-to-STL Agent Studio · Ender 5 S1
              {health && ` · ${health.llm_backend === "api" ? "API kredisi" : "Claude aboneliği"}`}
            </p>
          </div>
        </div>
        <button className="ghost-btn" onClick={onNewDesign} disabled={busy || messages.length === 0}>
          + Yeni tasarım
        </button>
      </header>

      {healthError && <div className="banner error">Backend'e ulaşılamıyor: {healthError}. Sunucu çalışıyor mu?</div>}

      <div className="chat-scroll" ref={scrollRef}>
        {messages.length === 0 && (
          <div className="welcome">
            <h2>Ne basmak istersin?</h2>
            <p>
              Fikrini Türkçe yaz; 4 uzman ajan planlasın, CAD kodunu yazsın, denetlesin ve 4 açıdan görsel kontrol
              yapsın. Sonuç Ender 5 S1 tablasında, baskıya hazır STL olarak sağda görünür.
            </p>
            <p>
              📎 STL'i olmayan bir ürün görmüşsen fotoğrafını ekle (klips ikonu veya yapıştır) — ajanlar görseli
              inceleyip ölçülerini tahmin ederek aynısının STL'ini çıkarsın.
            </p>
            <div className="examples">
              {EXAMPLES.map((e) => (
                <button key={e} className="chip" onClick={() => submit(e)} disabled={busy}>
                  {e}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m) => {
          if (m.role === "user")
            return (
              <div key={m.id} className="bubble user">
                {m.images?.length > 0 && (
                  <div className="attach-strip bubble-attachments">
                    {m.images.map((url, i) => (
                      <img key={i} src={url} alt="referans görsel" />
                    ))}
                  </div>
                )}
                {m.text}
              </div>
            );
          if (m.role === "system") return <div key={m.id} className="bubble system">{m.text}</div>;
          const job = jobs[m.jobId];
          return job ? <AgentTracker key={m.id} job={job} onOpenImage={onOpenImage} /> : null;
        })}
      </div>

      <form
        className="composer"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <div className="composer-main">
          {attachments.length > 0 && (
            <div className="attach-strip">
              {attachments.map((a) => (
                <div key={a.url} className="attach-chip">
                  <img src={a.url} alt="" />
                  <button type="button" className="attach-remove" onClick={() => removeAttachment(a.url)} title="Kaldır">
                    ×
                  </button>
                </div>
              ))}
            </div>
          )}
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
            onPaste={onPaste}
            rows={2}
            placeholder={
              hasModel
                ? "Modeli revize et… örn. 'kancayı 15 mm uzat, tabanı genişlet'"
                : "Örn. 'Masama kulaklık tutucu yap' veya bir ürün fotoğrafı ekle"
            }
            disabled={busy}
          />
        </div>
        <input
          ref={fileInputRef}
          type="file"
          accept={ACCEPTED_TYPES.join(",")}
          multiple
          hidden
          onChange={(e) => {
            addFiles(e.target.files);
            e.target.value = "";
          }}
        />
        <button
          type="button"
          className="attach-btn"
          onClick={() => fileInputRef.current?.click()}
          disabled={busy || attachments.length >= MAX_IMAGES}
          title="Ürün görseli ekle"
        >
          📎
        </button>
        <button className="send-btn" type="submit" disabled={busy || (!text.trim() && attachments.length === 0)}>
          {busy ? <span className="spinner" /> : hasModel ? "Revize et" : "Oluştur"}
        </button>
      </form>
    </aside>
  );
}
