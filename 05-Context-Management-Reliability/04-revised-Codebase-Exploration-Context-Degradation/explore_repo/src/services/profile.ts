import { Customer, CustomerDirectory } from "../repos/customer";

/** The fields a customer may change on the account page. */
export interface ProfileUpdate {
  name?: string;
  phone?: string;
  addressLines?: string[];
}

/** Reads and updates customer profiles; the email address is the login and never changes here. */
export class ProfileService {
  constructor(private readonly customers: CustomerDirectory) {}

  async profile(customerId: string): Promise<Customer> {
    const customer = await this.customers.findById(customerId);
    if (!customer) {
      throw new Error(`No customer ${customerId}`);
    }
    return customer;
  }

  async update(customerId: string, changes: ProfileUpdate): Promise<Customer> {
    const current = await this.profile(customerId);
    const updated: Customer = { ...current, ...changes, email: current.email };
    await this.customers.save(updated);
    return updated;
  }
}
