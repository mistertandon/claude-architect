import { ProfileService, ProfileUpdate } from "../services/profile";

/** The request and response shapes of the account endpoints. */
export interface AccountRequest {
  customerId: string;
  body?: ProfileUpdate;
}
export interface AccountResponse {
  status: number;
  body: unknown;
}

/** GET and PATCH /account: the customer's own profile page. */
export class AccountController {
  constructor(private readonly profiles: ProfileService) {}

  async get(request: AccountRequest): Promise<AccountResponse> {
    try {
      const customer = await this.profiles.profile(request.customerId);
      return { status: 200, body: { name: customer.name, email: customer.email, tier: customer.tier } };
    } catch {
      return { status: 404, body: { error: "account not found" } };
    }
  }

  async patch(request: AccountRequest): Promise<AccountResponse> {
    if (!request.body) {
      return { status: 400, body: { error: "nothing to update" } };
    }
    const customer = await this.profiles.update(request.customerId, request.body);
    return { status: 200, body: { name: customer.name, phone: customer.phone ?? null } };
  }
}
