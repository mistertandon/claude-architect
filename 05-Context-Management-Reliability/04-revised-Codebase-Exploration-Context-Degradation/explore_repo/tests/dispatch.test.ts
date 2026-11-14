import { DispatchService } from "../src/services/dispatch";
import { ShipmentStore } from "../src/repos/shipment";
import { OrderRepository } from "../src/repos/order";

describe("DispatchService", () => {
  it("keeps the order paid when the carrier refuses the label", async () => {
    const orders = new OrderRepository();
    await orders.save({ id: "ORD-7745", customerId: "CUST-1042", lines: [], status: "paid", createdAt: "2026-11-01T09:00:00Z" });
    const carrier = { buyLabel: async () => { throw new Error("address rejected"); } };
    const service = new DispatchService(new ShipmentStore(), carrier as never, orders);
    expect(await service.dispatch("ORD-7745", 900, ["410 Market St"])).toBe(false);
    expect((await orders.findById("ORD-7745"))?.status).toBe("paid");
  });
});
