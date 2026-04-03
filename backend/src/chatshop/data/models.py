from pydantic import BaseModel, Field


class Product(BaseModel):
    product_id: str
    title: str
    description: str = ""
    price: float | None = None
    brand: str = ""
    type: str = ""                      # "over-ear" | "in-ear" | "open-back"
    wireless: bool | None = None
    anc: bool | None = None
    battery_hours: int | None = None    # None for wired headphones
    waterproof_rating: str | None = None  # e.g. "IPX4", None if not rated
    driver_size_mm: float | None = None
    use_cases: list[str] = Field(default_factory=list)  # ["travel", "sport", ...]

    def to_document_text(self) -> str:
        """Text used for embedding — title + description only.

        Price and structured attributes are filter concerns, not semantic ones;
        keep them out of the embedding space.
        """
        parts = [self.title]
        if self.description:
            parts.append(self.description)
        return "\n".join(parts)

    def to_context_text(self) -> str:
        """Rich text for the LLM prompt — includes price and all attributes.

        Distinct from to_document_text(): the LLM needs all structured info to
        give good recommendations; the embedder only needs semantics.
        """
        lines = [self.title]
        if self.description:
            lines.append(self.description)

        attrs: list[str] = []
        if self.price is not None:
            attrs.append(f"Price: ${self.price:.2f}")
        if self.brand:
            attrs.append(f"Brand: {self.brand}")
        if self.type:
            attrs.append(f"Type: {self.type}")
        if self.wireless is not None:
            attrs.append(f"Wireless: {'Yes' if self.wireless else 'No'}")
        if self.anc is not None:
            attrs.append(f"ANC: {'Yes' if self.anc else 'No'}")
        if self.battery_hours is not None:
            attrs.append(f"Battery: {self.battery_hours}h")
        if self.waterproof_rating:
            attrs.append(f"Waterproof: {self.waterproof_rating}")
        if self.driver_size_mm is not None:
            attrs.append(f"Driver: {self.driver_size_mm}mm")
        if self.use_cases:
            attrs.append(f"Use cases: {', '.join(self.use_cases)}")
        if attrs:
            lines.append(" | ".join(attrs))
        return "\n".join(lines)

    def to_metadata(self) -> dict:
        """Flat dict stored alongside ChromaDB vectors.

        ChromaDB requires scalar values only and does not accept None.
        Absent optional fields use sentinels: -1 for numerics, "" for strings.
        use_cases is serialised as a CSV string for containment filtering.
        """
        return {
            "title": self.title,
            "description": self.description[:500],
            "price": self.price if self.price is not None else -1.0,
            "brand": self.brand,
            "type": self.type,
            "wireless": self.wireless if self.wireless is not None else False,
            "anc": self.anc if self.anc is not None else False,
            "battery_hours": self.battery_hours if self.battery_hours is not None else -1,
            "waterproof_rating": self.waterproof_rating or "",
            "driver_size_mm": self.driver_size_mm if self.driver_size_mm is not None else -1.0,
            "use_cases": ", ".join(self.use_cases),
        }
