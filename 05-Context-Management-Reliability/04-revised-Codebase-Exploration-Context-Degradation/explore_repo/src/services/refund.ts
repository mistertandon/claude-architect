import { PaymentLedger } from "../repos/payment";
import { PayFluxClient } from "../clients/payflux";

/** What a support agent fills in to refund an order. */
export interface RefundRequest {
  orderId: string;
  captureRef: string;
  amountCents: number;
  reason: string;
}

/** Issues refunds for captured payments and records each one in the ledger. */
export class RefundDesk {
  constructor(private readonly ledger: PaymentLedger, private readonly payflux: PayFluxClient) {}

  /** Refunds the amount through PayFlux, then records the refund entry. Returns PayFlux's refund reference. */
  async issueRefund(request: RefundRequest): Promise<string> {
    const balance = await this.ledger.balanceFor(request.orderId);
    if (request.amountCents > balance) {
      throw new Error(`A refund of ${request.amountCents} exceeds the captured balance of ${balance}`);
    }
    const result = await this.payflux.refund(request.captureRef, request.amountCents);
    await this.ledger.save({
      id: result.refundRef,
      orderId: request.orderId,
      amountCents: request.amountCents,
      kind: "refund",
      providerRef: result.refundRef,
      recordedAt: new Date().toISOString(),
    });
    return result.refundRef;
  }

  /** Every refund recorded for one order. */
  async refundsFor(orderId: string) {
    const entries = await this.ledger.list();
    return entries.filter((entry) => entry.orderId === orderId && entry.kind === "refund");
  }
}
