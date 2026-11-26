import { Hammer, Check } from "lucide-react";
import type { LucideIcon } from "lucide-react";

export default function Planned({ title, phase, text, items, icon: Icon }: { title: string; phase: number; text: string; items: string[]; icon: LucideIcon }) {
  return (
    <div className="glass grid h-full place-items-center rounded-[28px] p-8">
      <div className="w-full max-w-md text-center">
        <div className="mx-auto mb-5 grid h-16 w-16 place-items-center rounded-3xl glass-soft"><Icon size={26} className="text-nx-blue" /></div>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        <p className="mt-2 text-sm text-white/55">{text}</p>
        <ul className="mx-auto mt-6 space-y-2 text-left text-sm text-white/70">
          {items.map((i) => <li key={i} className="flex items-center gap-3 rounded-xl glass-soft px-4 py-2.5"><Check size={14} className="flex-none text-white/25" />{i}</li>)}
        </ul>
        <p className="mt-6 inline-flex items-center gap-2 rounded-full glass-soft px-3.5 py-1.5 text-xs text-white/65"><Hammer size={12} />Ikke bygget ennå · kommer i fase {phase}</p>
      </div>
    </div>
  );
}
