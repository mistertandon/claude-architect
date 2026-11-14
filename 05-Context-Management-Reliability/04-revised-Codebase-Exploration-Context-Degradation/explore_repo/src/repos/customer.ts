import { Repository } from "./base";

/** A Lumen Home customer account. */
export interface Customer {
  id: string;
  name: string;
  email: string;
  phone?: string;
  tier: "standard" | "silver" | "gold";
  addressLines: string[];
}

/** The directory of customer accounts, searchable by email. */
export class CustomerDirectory implements Repository<Customer> {
  private readonly customers = new Map<string, Customer>();

  async findById(id: string): Promise<Customer | undefined> {
    return this.customers.get(id);
  }

  async save(customer: Customer): Promise<void> {
    this.customers.set(customer.id, { ...customer, email: customer.email.toLowerCase() });
  }

  async list(): Promise<Customer[]> {
    return [...this.customers.values()];
  }

  /** The account with this email address, if any. */
  async byEmail(email: string): Promise<Customer | undefined> {
    const wanted = email.trim().toLowerCase();
    return [...this.customers.values()].find((customer) => customer.email === wanted);
  }
}
