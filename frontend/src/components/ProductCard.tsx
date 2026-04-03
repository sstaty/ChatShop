import Image from "next/image";

import { ProductVisualType } from "@/lib/agentState";

export interface ProductCardProps {
  name: string;
  price?: number;
  type: ProductVisualType;
  badge: string;
  rationale: string;
  keyAttrs: string[];
}

const BADGE_STYLES: Record<string, { background: string; text: string }> = {
  "best match": { background: "#534AB7", text: "#EEEDFE" },
  "best value": { background: "#0F6E56", text: "#E1F5EE" },
  "luxury pick": { background: "#3C3489", text: "#CECBF6" },
  "hidden gem": { background: "#854F0B", text: "#FAEEDA" },
  recommended: {
    background: "var(--color-background-secondary)",
    text: "var(--color-text-secondary)",
  },
};

const TYPE_IMAGES: Record<ProductVisualType, { src: string; alt: string; label: string }> = {
  "in-ear": { src: "/in%20ear.jpg", alt: "In-ear headphones", label: "In-ear" },
  "on-ear": { src: "/on%20ear.jpg", alt: "On-ear headphones", label: "On-ear" },
  "over-ear": { src: "/over%20ear.jpg", alt: "Over-ear headphones", label: "Over-ear" },
};

function getBadgeStyle(badge: string) {
  return BADGE_STYLES[badge.toLowerCase()] ?? BADGE_STYLES.recommended;
}

export function ProductCard({ name, price, type, badge, rationale, keyAttrs }: ProductCardProps) {
  const badgeStyle = getBadgeStyle(badge);
  const image = TYPE_IMAGES[type];
  const formattedPrice = typeof price === "number" ? `$${price.toFixed(0)}` : null;

  return (
    <article
      className="surface-card-strong flex h-full w-full max-w-[380px] min-w-[260px] md:min-w-[280px] flex-col overflow-hidden rounded-[1.7rem]"
      style={{ background: `linear-gradient(160deg, ${badgeStyle.background}28 0%, rgba(255,255,255,0) 50%), rgba(255,255,255,0.94)` }}
    >
      <div
        className="px-4 py-1.5 text-[11px] font-semibold uppercase tracking-[0.18em]"
        style={{ backgroundColor: badgeStyle.background, color: badgeStyle.text }}
      >
        {badge}
      </div>

      <div className="flex flex-1 flex-col p-3">
        <div className="relative overflow-hidden rounded-[1.25rem] border border-(--color-border-tertiary) bg-[linear-gradient(180deg,rgba(255,255,255,0.82),rgba(240,248,255,0.96))]" style={{ height: "var(--card-img-h)" }}>
            <Image
              src={image.src}
              alt={image.alt}
              fill
              sizes="(max-width: 768px) 256px, 224px"
              className="object-cover"
            />
        </div>

        <div className="mt-2 flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="section-label">{image.label}</p>
            <h3 className="mt-1 text-balance text-[1.1rem] font-semibold leading-6 tracking-[-0.02em] text-(--color-text-primary)">
              {name}
            </h3>
            {formattedPrice && (
              <p className="mt-1 text-[1.02rem] font-semibold tracking-[-0.01em] text-(--color-accent-strong)">
                {formattedPrice}
              </p>
            )}
          </div>
        </div>

        <p className="rationale-clamp mt-2 text-[13px] leading-[1.5] text-(--color-text-secondary)">{rationale}</p>

        <div className="mt-auto flex flex-wrap gap-2 pt-3">
          {keyAttrs.map((attr) => (
            <span key={attr} className="product-chip">
              {attr}
            </span>
          ))}
        </div>
      </div>
    </article>
  );
}