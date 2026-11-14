import { OrderService } from "../src/services/order";
import { OrderRepository } from "../src/repos/order";
import { StockKeeper } from "../src/repos/stock";
import { PaymentLedger } from "../src/repos/payment";

describe("OrderService", () => {
  it("reserves stock and records the capture", async () => {
    const stock = new StockKeeper();
    await stock.save({ id: "s1", sku: "AUR-DL-01", onHand: 5, reserved: 0, reorderPoint: 1, reorderQuantity: 10 });
    const ledger = new PaymentLedger();
    const service = new OrderService(new OrderRepository(), stock, ledger);
    const order = await service.placeOrder({
      customerId: "CUST-1042",
      lines: [{ sku: "AUR-DL-01", quantity: 2, unitPriceCents: 4999 }],
      captureRef: "pf-cap-1",
    });
    expect(order.status).toBe("paid");
    expect(await ledger.balanceFor(order.id)).toBe(9998);
  });
});
