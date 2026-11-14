import { Order, OrderLine, OrderRepository, orderTotalCents } from "../repos/order";
import { StockKeeper } from "../repos/stock";
import { PaymentLedger } from "../repos/payment";

/** What the checkout page sends when a customer places an order. */
export interface PlaceOrderInput {
  customerId: string;
  lines: OrderLine[];
  captureRef: string;
}

/** Places orders: reserves stock, records the captured payment and saves the order. */
export class OrderService {
  constructor(
    private readonly orders: OrderRepository,
    private readonly stock: StockKeeper,
    private readonly ledger: PaymentLedger,
  ) {}

  async placeOrder(input: PlaceOrderInput): Promise<Order> {
    for (const line of input.lines) {
      const reserved = await this.stock.reserve(line.sku, line.quantity);
      if (!reserved) {
        throw new Error(`Not enough stock for ${line.sku}`);
      }
    }
    const order: Order = {
      id: `ORD-${Date.now()}`,
      customerId: input.customerId,
      lines: input.lines,
      status: "paid",
      createdAt: new Date().toISOString(),
    };
    await this.orders.save(order);
    await this.ledger.save({
      id: `cap-${order.id}`,
      orderId: order.id,
      amountCents: orderTotalCents(order),
      kind: "capture",
      providerRef: input.captureRef,
      recordedAt: order.createdAt,
    });
    return order;
  }

  async cancel(orderId: string): Promise<void> {
    const order = await this.orders.findById(orderId);
    if (order && order.status === "paid") {
      await this.orders.save({ ...order, status: "cancelled" });
    }
  }
}
