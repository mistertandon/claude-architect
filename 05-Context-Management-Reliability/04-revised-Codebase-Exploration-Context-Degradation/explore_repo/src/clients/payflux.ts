/** The answer PayFlux gives to a refund request. */
export interface PayFluxRefund {
  refundRef: string;
  status: "accepted" | "pending";
}

const PAYFLUX_URL = "https://api.payflux.example/v2";

/** A thin client for the PayFlux payments API. */
export class PayFluxClient {
  constructor(private readonly apiKey: string, private readonly timeoutMs = 8000) {}

  /** Asks PayFlux to refund part or all of a captured payment. Throws on any non-2xx answer. */
  async refund(captureRef: string, amountCents: number): Promise<PayFluxRefund> {
    const response = await fetch(`${PAYFLUX_URL}/refunds`, {
      method: "POST",
      headers: { authorization: `Bearer ${this.apiKey}`, "content-type": "application/json" },
      body: JSON.stringify({ capture: captureRef, amount: amountCents }),
      signal: AbortSignal.timeout(this.timeoutMs),
    });
    if (!response.ok) {
      throw new Error(`PayFlux refund failed with status ${response.status}`);
    }
    return (await response.json()) as PayFluxRefund;
  }

  /** The current state of an earlier refund. */
  async refundStatus(refundRef: string): Promise<PayFluxRefund> {
    const response = await fetch(`${PAYFLUX_URL}/refunds/${encodeURIComponent(refundRef)}`, {
      headers: { authorization: `Bearer ${this.apiKey}` },
      signal: AbortSignal.timeout(this.timeoutMs),
    });
    if (!response.ok) {
      throw new Error(`PayFlux status lookup failed with status ${response.status}`);
    }
    return (await response.json()) as PayFluxRefund;
  }
}
