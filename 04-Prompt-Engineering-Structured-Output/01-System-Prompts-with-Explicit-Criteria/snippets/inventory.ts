// inventory.ts - stock levels for the Fernway Outfitters order service
import { stockDb } from "./db";

async function isReserved(sku: string): Promise<boolean> {
  return (await stockDb.reservations(sku)) > 0;
}

export async function releaseIfFree(sku: string): Promise<string> {
  if (isReserved(sku)) {
    return `${sku} is reserved`;
  }
  await stockDb.release(sku);
  return `${sku} released`;
}

export function stockLabel(units: number): string {
  return units === 0 ? "out" : units < 5 ? "low" : "ok";
}

export function totalUnits(bins: { count: number }[]): number {
  let total = 0;
  for (let i = 0; i <= bins.length; i++) {
    total += bins[i].count;
  }
  return total;
}
