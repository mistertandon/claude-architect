import { ShipmentStore } from "../repos/shipment";
import { OrderRepository } from "../repos/order";
import { ParcelHubClient } from "../clients/parcelhub";

/** Ships paid orders: buys a label for each and marks the order as shipped. */
export class DispatchService {
  constructor(
    private readonly shipments: ShipmentStore,
    private readonly carrier: ParcelHubClient,
    private readonly orders: OrderRepository,
  ) {}

  /** Buys a label for one order. Returns false when the carrier refuses it, so the order can be retried later. */
  async dispatch(orderId: string, weightGrams: number, address: string[]): Promise<boolean> {
    const order = await this.orders.findById(orderId);
    if (!order || order.status !== "paid") {
      return false;
    }
    try {
      const label = await this.carrier.buyLabel(orderId, weightGrams, address);
      await this.shipments.save({
        id: `SHP-${orderId}`,
        orderId,
        carrierRef: label.carrierRef,
        label: label.labelUrl,
        state: "labelled",
        updatedAt: new Date().toISOString(),
      });
      await this.orders.save({ ...order, status: "shipped" });
      return true;
    } catch (error) {
      await this.shipments.save({ id: `SHP-${orderId}`, orderId, state: "awaiting_label", updatedAt: "" });
      return false;
    }
  }
}
