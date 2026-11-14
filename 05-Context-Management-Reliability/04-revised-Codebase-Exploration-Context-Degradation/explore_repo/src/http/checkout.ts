import { OrderService, PlaceOrderInput } from "../services/order";

/** The minimal request and response shapes the HTTP layer works with. */
export interface HttpRequest {
  body: unknown;
  params: Record<string, string>;
}
export interface HttpResponse {
  status: number;
  body: unknown;
}

/** POST /checkout: turns a checkout form into an order. */
export class CheckoutController {
  constructor(private readonly orderService: OrderService) {}

  async post(request: HttpRequest): Promise<HttpResponse> {
    const input = request.body as PlaceOrderInput;
    if (!input?.customerId || !Array.isArray(input.lines) || input.lines.length === 0) {
      return { status: 400, body: { error: "customerId and at least one line are required" } };
    }
    try {
      const order = await this.orderService.placeOrder(input);
      return { status: 201, body: { orderId: order.id, status: order.status } };
    } catch (error) {
      return { status: 409, body: { error: String(error) } };
    }
  }

  /** DELETE /checkout/:orderId cancels a paid order. */
  async delete(request: HttpRequest): Promise<HttpResponse> {
    await this.orderService.cancel(request.params.orderId);
    return { status: 204, body: null };
  }
}
