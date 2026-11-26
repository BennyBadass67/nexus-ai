import type { Level } from "../api";

const C: Record<string, string> = {
  green: "bg-emerald-400 shadow-[0_0_10px_rgba(52,211,153,.8)]",
  yellow: "bg-amber-400 shadow-[0_0_10px_rgba(251,191,36,.7)]",
  red: "bg-rose-500 shadow-[0_0_10px_rgba(244,63,94,.7)]",
  unknown: "bg-white/25",
};
export const LABEL: Record<string, string> = { green: "Anbefalt for PC-en din", yellow: "Går, men tregt", red: "For tung for PC-en din", unknown: "Ukjent" };

export default function Dot({ level, reason, size = 9 }: { level?: Level; reason?: string; size?: number }) {
  const l = level || "unknown";
  return <span title={`${LABEL[l]}${reason ? ". " + reason : ""}`} className={`inline-block flex-none rounded-full ${C[l]}`} style={{ width: size, height: size }} />;
}
