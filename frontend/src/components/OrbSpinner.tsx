interface OrbSpinnerProps {
  message: string;
  detail?: string;
}

const RINGS = [
  { size: 80, color: "#534AB7", duration: "1.2s", reverse: false },
  { size: 56, color: "#7B74D4", duration: "0.9s", reverse: true },
  { size: 32, color: "#A9A3E8", duration: "0.6s", reverse: false },
] as const;

export function OrbSpinner({ message, detail = "" }: OrbSpinnerProps) {
  return (
    <>
      <div className="flex flex-col items-center gap-4 text-center sm:flex-row sm:items-center sm:text-left">
        <div className="relative flex h-20 w-20 shrink-0 items-center justify-center">
          {RINGS.map(({ size, color, duration, reverse }) => (
            <span
              key={size}
              className="absolute inline-block rounded-full border-2 border-transparent"
              style={{
                width: size,
                height: size,
                borderTopColor: color,
                animation: `orb-spin ${duration} linear infinite${reverse ? " reverse" : ""}`,
              }}
            />
          ))}
        </div>
        <div>
          <p className="text-sm font-medium text-slate-700">{message}</p>
          {detail ? <p className="mt-1 text-xs text-slate-400">{detail}</p> : null}
        </div>
      </div>
      <style>{`
        @keyframes orb-spin { to { transform: rotate(360deg); } }
      `}</style>
    </>
  );
}