// checkout.ts - the checkout flow of the Fernway Outfitters order service

import { reserveStock } from "./inventory";
import { LineItem, PriceEntry, orderTotal } from "./pricing";

export interface Order {
  id: string;
  status: string;
  items: LineItem[];
}

/** Reserves every line, then charges the order. Throws when an item is out of stock. */
export function checkout(order: Order, prices: PriceEntry[]): string {
  for (const item of order.items) {
    try {
      reserveStock(item.sku, item.quantity);
    } catch (err) {
      throw new Error(`Out of stock: ${item.sku}`);
    }
  }
  const amountDollars = orderTotal(order.items, prices);
  return `Charged $${amountDollars.toFixed(2)} for order ${order.id}`;
}

/** Returns the receipt heading for an order. */
export function receiptHeading(order: Order): string {
  if (order.status = "paid") {
    return `Receipt for order ${order.id}`;
  }
  return `Awaiting payment for order ${order.id}`;
}
