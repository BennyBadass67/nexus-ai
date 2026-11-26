import { useState } from "react";
import { Send, Copy, Check, Mail } from "lucide-react";

const TO = "ti0xu1@mail.instinct.com";
const FROM = "belehansen@gmail.com";

export function buildMailto(subject: string, body: string) {
  return `mailto:${TO}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
}

export default function InstinctPage() {
  const [subject, setSubject] = useState("Melding fra NEXUS");
  const [body, setBody] = useState(""); const [copied, setCopied] = useState(false);
  const field = "w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm outline-none focus:border-nx-blue/60";
  const copy = async () => { try { await navigator.clipboard.writeText(`Til: ${TO}\nEmne: ${subject}\n\n${body}`); setCopied(true); setTimeout(() => setCopied(false), 2000); } catch { /* ignore */ } };
  return (
    <div className="glass flex h-full flex-col overflow-hidden rounded-[28px] p-6">
      <h1 className="text-xl font-semibold">Instinct</h1>
      <p className="text-sm text-white/65">Skriv en melding til Instinct herfra. Den åpnes ferdig utfylt i e-postprogrammet ditt, og du trykker Send der. Svar kommer på WhatsApp som vanlig.</p>
      <div className="mt-5 flex max-w-2xl flex-col gap-3">
        <div className="flex items-center gap-2 text-sm text-white/80"><Mail size={15} />Til: <b data-testid="to">{TO}</b></div>
        <input className={field} value={subject} onChange={(e) => setSubject(e.target.value)} placeholder="Emne" />
        <textarea className={`${field} h-48 resize-none`} value={body} onChange={(e) => setBody(e.target.value)} placeholder="Skriv meldingen din til Instinct her…" />
        <div className="flex flex-wrap items-center gap-2">
          <a href={buildMailto(subject, body)} className={`flex items-center gap-2 rounded-xl bg-nx-blue px-4 py-2.5 text-sm font-medium text-white ${body.trim() ? "" : "pointer-events-none opacity-50"}`} aria-disabled={!body.trim()}><Send size={15} />Åpne i e-post</a>
          <button onClick={copy} disabled={!body.trim()} className="glass-soft flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm disabled:opacity-50">{copied ? <Check size={15} /> : <Copy size={15} />}{copied ? "Kopiert" : "Kopier"}</button>
        </div>
        <p className="text-xs text-white/70">Avsender blir den e-postkontoen som er satt som standard i e-postprogrammet ditt. Bruk {FROM}, så vet Instinct at det er deg. Hvis ingenting åpner seg, trykk Kopier og lim inn i e-posten.</p>
      </div>
    </div>
  );
}
