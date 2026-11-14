/** A purchase order line as the Kestrel Supply EDI feed expects it. */
export interface SupplierOrderLine {
  sku: string;
  quantity: number;
}

const KESTREL_EDI_URL = "https://edi.kestrelsupply.example/inbound";

/** Sends purchase orders to Kestrel Supply over its EDI feed. */
export class SupplierBridge {
  constructor(private readonly partnerId: string) {}

  /** Places a purchase order for one SKU; returns Kestrel's order reference. Throws when the feed rejects it. */
  async placeOrder(sku: string, quantity: number): Promise<string> {
    const lines: SupplierOrderLine[] = [{ sku, quantity }];
    const response = await fetch(KESTREL_EDI_URL, {
      method: "POST",
      headers: { "x-partner-id": this.partnerId, "content-type": "application/json" },
      body: JSON.stringify({ type: "850", lines }),
    });
    if (!response.ok) {
      throw new Error(`Kestrel Supply rejected the order: status ${response.status}`);
    }
    const body = (await response.json()) as { orderRef: string };
    return body.orderRef;
  }
}
