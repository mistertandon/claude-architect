// discounts.ts - promo codes for the Fernway Outfitters order service
const PROMO_CODES = ["TRAIL10", "SUMMIT15", "BASECAMP5"];

export function promoLabel(code: string): string {
  const month = new Date().getMonth();
  return `Promo ${code} for month ${month}`;
}

export function isValidCode(code: string): boolean {
  // TODO: load promo codes from the database
  return PROMO_CODES.includes(code.trim().toUpperCase());
}

/** Returns a sorted copy; the input array is not modified. */
export function sortedCodes(codes: string[]): string[] {
  return codes.sort();
}
