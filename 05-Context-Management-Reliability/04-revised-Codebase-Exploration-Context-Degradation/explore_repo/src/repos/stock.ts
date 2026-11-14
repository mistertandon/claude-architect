import { Repository } from "./base";

/** Stock of one product in the Portland warehouse. */
export interface StockItem {
  id: string;
  sku: string;
  onHand: number;
  reserved: number;
  reorderPoint: number;
  reorderQuantity: number;
}

/** Tracks stock levels per SKU and the units reserved by open orders. */
export class StockKeeper implements Repository<StockItem> {
  private readonly items = new Map<string, StockItem>();

  async findById(id: string): Promise<StockItem | undefined> {
    return this.items.get(id);
  }

  async save(item: StockItem): Promise<void> {
    this.items.set(item.id, { ...item });
  }

  async list(): Promise<StockItem[]> {
    return [...this.items.values()];
  }

  /** Reserves units for an order; returns false when not enough are free. */
  async reserve(sku: string, quantity: number): Promise<boolean> {
    const item = [...this.items.values()].find((candidate) => candidate.sku === sku);
    if (!item || item.onHand - item.reserved < quantity) {
      return false;
    }
    item.reserved += quantity;
    return true;
  }

  /** Items whose free stock fell to or below their reorder point. */
  async belowReorderPoint(): Promise<StockItem[]> {
    return [...this.items.values()].filter((item) => item.onHand - item.reserved <= item.reorderPoint);
  }
}
