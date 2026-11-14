// pricing.ts - order totals and bulk discounts for the Fernway Outfitters order service

export interface LineItem {
  sku: string;
  quantity: number;
}

export interface PriceEntry {
  sku: string;
  unitPriceCents: number;
}

/** Returns the order total in integer cents. */
export function orderTotal(items: LineItem[], prices: PriceEntry[]): number {
  const unitPriceCents = new Map(prices.map((entry) => [entry.sku, entry.unitPriceCents]));
  let totalCents = 0;
  for (const item of items) {
    totalCents += (unitPriceCents.get(item.sku) ?? 0) * item.quantity;
  }
  return totalCents;
}

/** Returns the discount percent of the highest tier the quantity reaches (5% per tier). */
export function bulkDiscountPercent(quantity: number, tiers: number[]): number {
  let percent = 0;
  for (let i = 0; i <= tiers.length; i++) {
    if (quantity >= tiers[i]) percent = (i + 1) * 5;
  }
  return percent;
}

/** Returns the display name of each priced row. */
export function pricedNames(rows: { id: string }[], lookup: { id: string; name: string }[]): string[] {
  const names: string[] = [];
  rows.forEach((row) => {
    const match = lookup.find((entry) => entry.id === row.id);
    if (match) names.push(match.name);
  });
  return names;
}
