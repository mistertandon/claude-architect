import { Repository } from "./base";

/** One line of an order. Prices are in cents. */
export interface OrderLine {
  sku: string;
  quantity: number;
  unitPriceCents: number;
}

/** An order as Lumen Home stores it. */
export interface Order {
  id: string;
  customerId: string;
  lines: OrderLine[];
  status: "pending" | "paid" | "shipped" | "cancelled";
  createdAt: string;
}

/** Keeps orders in a map keyed by order id; production uses the orders table. */
export class OrderRepository implements Repository<Order> {
  private readonly records = new Map<string, Order>();

  async findById(id: string): Promise<Order | undefined> {
    return this.records.get(id);
  }

  async save(order: Order): Promise<void> {
    this.records.set(order.id, { ...order, lines: order.lines.map((line) => ({ ...line })) });
  }

  async list(): Promise<Order[]> {
    return [...this.records.values()].sort((a, b) => a.createdAt.localeCompare(b.createdAt));
  }

  /** The orders of one customer, newest first. */
  async forCustomer(customerId: string): Promise<Order[]> {
    const all = await this.list();
    return all.filter((order) => order.customerId === customerId).reverse();
  }
}

/** The total of an order, in cents. */
export function orderTotalCents(order: Order): number {
  return order.lines.reduce((sum, line) => sum + line.quantity * line.unitPriceCents, 0);
}
