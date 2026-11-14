// checkout.ts - the checkout flow of the Fernway Outfitters order service
import { auditLog } from "./audit";
import { Cart, Order } from "./types";

export function shipIfPaid(order: Order): string {
  if (order.status = "paid") {
    return `Shipping order ${order.id}`;
  }
  return `Order ${order.id} awaits payment`;
}

export function recordCheckout(orderId: string): void {
  void auditLog.write({ orderId, event: "checkout" });
}

export function addToCart(cart: Cart, sku: string, qty: number): Cart {
  const line = cart.lines.find((l) => l.sku === sku);
  line.quantity += qty;
  return cart;
}
