import { ProfileService } from "../src/services/profile";
import { CustomerDirectory } from "../src/repos/customer";

describe("ProfileService", () => {
  it("never changes the email address", async () => {
    const customers = new CustomerDirectory();
    await customers.save({ id: "CUST-2077", name: "Sam Okafor", email: "sam.okafor@example.com", tier: "silver", addressLines: [] });
    const service = new ProfileService(customers);
    const updated = await service.update("CUST-2077", { phone: "+1-206-555-0177" });
    expect(updated.email).toBe("sam.okafor@example.com");
    expect(updated.phone).toBe("+1-206-555-0177");
  });
});
