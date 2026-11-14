import { StockKeeper } from "../repos/stock";
import { SupplierBridge } from "../clients/supplier";

/** The outcome of one reorder attempt. */
export interface ReorderResult {
  sku: string;
  ordered: number;
  supplierRef?: string;
  error?: string;
}

/** Runs nightly: orders more of every SKU whose free stock fell below its reorder point. */
export class ReorderPlanner {
  constructor(private readonly stock: StockKeeper, private readonly supplier: SupplierBridge) {}

  async run(): Promise<ReorderResult[]> {
    const low = await this.stock.belowReorderPoint();
    const results: ReorderResult[] = [];
    for (const item of low) {
      try {
        const supplierRef = await this.supplier.placeOrder(item.sku, item.reorderQuantity);
        results.push({ sku: item.sku, ordered: item.reorderQuantity, supplierRef });
      } catch (error) {
        results.push({ sku: item.sku, ordered: 0, error: String(error) });
      }
    }
    return results;
  }
}
