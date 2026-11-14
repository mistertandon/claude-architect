import { Repository } from "./base";

/** A message waiting to be sent to a customer. */
export interface Notice {
  id: string;
  customerId: string;
  template: "order_confirmed" | "order_shipped" | "refund_issued";
  payload: Record<string, string>;
  attempts: number;
  sentAt?: string;
}

/** A queue of notices; a notice stays queued until it is marked as sent. */
export class NoticeQueue implements Repository<Notice> {
  private readonly notices: Notice[] = [];

  async findById(id: string): Promise<Notice | undefined> {
    return this.notices.find((notice) => notice.id === id);
  }

  async save(notice: Notice): Promise<void> {
    const index = this.notices.findIndex((existing) => existing.id === notice.id);
    if (index >= 0) {
      this.notices[index] = { ...notice };
    } else {
      this.notices.push({ ...notice });
    }
  }

  async list(): Promise<Notice[]> {
    return [...this.notices];
  }

  /** Notices not sent yet, oldest first. */
  async pending(): Promise<Notice[]> {
    return this.notices.filter((notice) => !notice.sentAt);
  }
}
