import { RefundDesk } from "../src/services/refund";
import { PaymentLedger } from "../src/repos/payment";

describe("RefundDesk", () => {
  it("records a refund entry after PayFlux accepts it", async () => {
    const ledger = new PaymentLedger();
    await ledger.save({ id: "cap-1", orderId: "ORD-7731", amountCents: 4999, kind: "capture", providerRef: "pf-1", recordedAt: "2026-10-03T10:00:00Z" });
    const payflux = { refund: async () => ({ refundRef: "rf-1", status: "accepted" as const }) };
    const desk = new RefundDesk(ledger, payflux as never);
    expect(await desk.issueRefund({ orderId: "ORD-7731", captureRef: "pf-1", amountCents: 4999, reason: "damaged" })).toBe("rf-1");
    expect(await ledger.balanceFor("ORD-7731")).toBe(0);
  });
});
