export type AgentState =
  | { status: "idle" }
  | { status: "thinking"; message: string; detail: string }
  | { status: "intent"; summary: string; semanticQuery: string; filters: Record<string, unknown> }
  | { status: "results"; items: ProductItem[] }
  | { status: "clarify" }

export interface ProductItem {
  product_id: string
  badge: string
  rationale: string
  key_attrs: string[]
  [key: string]: unknown
}
