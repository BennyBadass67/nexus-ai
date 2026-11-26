import { useEffect, useState } from "react";

// Introanimasjon ved oppstart (ren CSS, ingen videofil). Trykk eller Esc hopper over.
export default function Intro({ name }: { name: string }) {
  const [gone, setGone] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setGone(true), 3900);
    const k = (e: KeyboardEvent) => e.key === "Escape" && setGone(true);
    window.addEventListener("keydown", k);
    return () => { clearTimeout(t); window.removeEventListener("keydown", k); };
  }, []);
  if (gone) return null;
  return (
    <div className="intro" data-testid="intro" onClick={() => setGone(true)}>
      <div className="ring" /><div className="ring r2" />
      <div className="relative flex flex-col items-center gap-5">
        <img src="/logo.png" alt="" className="logo" />
        <div className="word text-[34px] font-semibold tracking-[.28em] text-white">{name.toUpperCase().split("").map((c, i) => <span key={i} style={{ animationDelay: `${0.7 + i * 0.07}s` }}>{c === " " ? "\u00a0" : c}</span>)}</div>
        <div className="tag text-sm text-white">Din lokale AI. Ingen sky.</div>
      </div>
      <div className="skip">trykk for å hoppe over</div>
    </div>
  );
}
