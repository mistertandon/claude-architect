import { Repository } from "./base";

/** A captured card payment or a refund. Amounts are in cents. */
export interface Payment {
  id: string;
  orderId: string;
  amountCents: number;
  kind: "capture" | "refund";
  providerRef: string;
  recordedAt: string;
}

/**
 * An append-only ledger of payment events: a refund is a new entry, never an
 * update of the capture it reverses.
 */
export class PaymentLedger implements Repository<Payment> {
  private readonly entries: Payment[] = [];

  async findById(id: string): Promise<Payment | undefined> {
    return this.entries.find((entry) => entry.id === id);
  }

  async save(payment: Payment): Promise<void> {
    this.entries.push({ ...payment });
  }

  async list(): Promise<Payment[]> {
    return [...this.entries];
  }

  /** The net amount captured for an order: captures minus refunds, in cents. */
  async balanceFor(orderId: string): Promise<number> {
    return this.entries
      .filter((entry) => entry.orderId === orderId)
      .reduce((sum, entry) => sum + (entry.kind === "capture" ? entry.amountCents : -entry.amountCents), 0);
  }
}
