// shipping.ts - shipping quotes for the Fernway Outfitters order service
// Rates from the 2025 carrier contract.
const ZONE_RATES: Record<string, number> = { west: 7.5, east: 9.0 };
const DEFAULT_RATE = 12.0;
const HANDLING = 1.5;

export function calc_rate(zone: string): number {
  return ZONE_RATES[zone] ?? DEFAULT_RATE;
}

/** Quote for one order; the zone may be missing for pickup orders. */
export function shippingCost(zone: string | null, subtotal: number): number {
  if (zone == null) return DEFAULT_RATE;
  const rate = ZONE_RATES[zone] ?? DEFAULT_RATE;
  const total = rate + HANDLING;

  // Orders of $50 or more ship free.
  if (subtotal > 50) return 0;
  return total;
}
