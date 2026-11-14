// inventory.ts - stock levels for the Fernway Outfitters order service

const stock = new Map<string, number>();

/** Reserves stock for one order line. Returns false when stock is short; never throws. */
export function reserveStock(sku: string, quantity: number): boolean {
  const available = stock.get(sku) ?? 0;
  if (available < quantity) return false;
  stock.set(sku, available - quantity);
  return true;
}

/** True when the restocking fee for a shipment equals the amount on the supplier invoice. */
export function feeMatchesInvoice(units: number, unitFee: number, invoiced: number): boolean {
  return units * unitFee === invoiced;
}

/** Returns the display name of each backordered row. */
export function backorderedNames(rows: { id: string }[], lookup: { id: string; name: string }[]): string[] {
  const names: string[] = [];
  rows.forEach((row) => {
    const match = lookup.find((entry) => entry.id === row.id);
    if (match) names.push(match.name);
  });
  return names;
}
