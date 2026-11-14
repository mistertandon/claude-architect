/** A shipping label bought from ParcelHub. */
export interface ParcelLabel {
  carrierRef: string;
  labelUrl: string;
}

const PARCELHUB_URL = "https://api.parcelhub.example/v1";

/** Buys shipping labels and reads tracking states from the ParcelHub carrier API. */
export class ParcelHubClient {
  constructor(private readonly token: string) {}

  /** Buys a label for a parcel. Throws when ParcelHub refuses the address or the weight. */
  async buyLabel(orderId: string, weightGrams: number, address: string[]): Promise<ParcelLabel> {
    const response = await fetch(`${PARCELHUB_URL}/labels`, {
      method: "POST",
      headers: { authorization: `Token ${this.token}`, "content-type": "application/json" },
      body: JSON.stringify({ reference: orderId, weight: weightGrams, address }),
    });
    if (!response.ok) {
      throw new Error(`ParcelHub label request failed with status ${response.status}`);
    }
    return (await response.json()) as ParcelLabel;
  }

  /** The carrier's latest tracking state for a parcel. */
  async trackingState(carrierRef: string): Promise<string> {
    const response = await fetch(`${PARCELHUB_URL}/tracking/${encodeURIComponent(carrierRef)}`, {
      headers: { authorization: `Token ${this.token}` },
    });
    const body = (await response.json()) as { state: string };
    return body.state;
  }
}
