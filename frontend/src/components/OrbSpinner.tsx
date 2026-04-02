interface OrbSpinnerProps {
  message: string;
  detail?: string;
}

const RINGS = [
  { size: 80, color: "var(--color-accent)", duration: "1.2s", reverse: false },
  { size: 56, color: "#38bdf8", duration: "0.9s", reverse: true },
  { size: 32, color: "#7dd3fc", duration: "0.6s", reverse: false },
] as const;

export function OrbSpinner({ message, detail = "" }: OrbSpinnerProps) {
  return (
    <>
      <div className="flex max-w-xl flex-col items-center gap-5 text-center">
        <div className="relative flex h-20 w-20 shrink-0 items-center justify-center rounded-full bg-[var(--color-accent-soft)]">
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
        <div className="space-y-1.5">
          <p className="text-base font-semibold tracking-[-0.01em] text-[var(--color-text-primary)] md:text-[1.05rem]">
            {message}
          </p>
          {detail ? (
            <p className="text-sm leading-6 text-[var(--color-text-secondary)] md:text-[0.95rem]">
              {detail}
            </p>
          ) : null}
        </div>
      </div>
      <style>{`
        @keyframes orb-spin { to { transform: rotate(360deg); } }
      `}</style>
    </>
  );
}