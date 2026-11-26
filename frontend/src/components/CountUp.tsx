import { useEffect, useState } from "react";

/** Teller opp et heltall fra 0. Hopper rett til sluttverdien ved «reduser bevegelse». */
export default function CountUp({ value, ms = 800 }: { value: number; ms?: number }) {
  const [n, setN] = useState(0);
  useEffect(() => {
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches || value <= 0) { setN(value); return; }
    let raf = 0; const t0 = performance.now();
    const step = (t: number) => { const k = Math.min(1, (t - t0) / ms); setN(Math.round(value * (1 - Math.pow(1 - k, 3)))); if (k < 1) raf = requestAnimationFrame(step); };
    raf = requestAnimationFrame(step); return () => cancelAnimationFrame(raf);
  }, [value, ms]);
  return <span data-final={value}>{n}</span>;
}
