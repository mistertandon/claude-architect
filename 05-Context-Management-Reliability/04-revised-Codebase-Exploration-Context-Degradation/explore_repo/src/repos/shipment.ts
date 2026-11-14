import { Repository } from "./base";

/** A parcel handed to a carrier for one order. */
export interface Shipment {
  id: string;
  orderId: string;
  carrierRef?: string;
  label?: string;
  state: "awaiting_label" | "labelled" | "in_transit" | "delivered";
  updatedAt: string;
}

/** Stores shipments, one per parcel; an order can ship in several parcels. */
export class ShipmentStore implements Repository<Shipment> {
  private readonly shipments = new Map<string, Shipment>();

  async findById(id: string): Promise<Shipment | undefined> {
    return this.shipments.get(id);
  }

  async save(shipment: Shipment): Promise<void> {
    this.shipments.set(shipment.id, { ...shipment, updatedAt: new Date().toISOString() });
  }

  async list(): Promise<Shipment[]> {
    return [...this.shipments.values()];
  }

  /** Every parcel of one order. */
  async forOrder(orderId: string): Promise<Shipment[]> {
    return [...this.shipments.values()].filter((shipment) => shipment.orderId === orderId);
  }
}
