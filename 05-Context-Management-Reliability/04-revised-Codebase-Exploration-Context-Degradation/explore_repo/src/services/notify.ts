import { NoticeQueue } from "../repos/notice";
import { MailRelay } from "../clients/mailrelay";

const MAX_ATTEMPTS = 5;

/** Sends queued customer notices by email; a failed send stays queued for the next run. */
export class NotifyService {
  constructor(private readonly queue: NoticeQueue, private readonly mail: MailRelay) {}

  /** Sends every pending notice. Returns how many were sent. */
  async flush(emailFor: (customerId: string) => string): Promise<number> {
    let sent = 0;
    for (const notice of await this.queue.pending()) {
      if (notice.attempts >= MAX_ATTEMPTS) {
        continue;
      }
      try {
        await this.mail.send({ to: emailFor(notice.customerId), template: notice.template, variables: notice.payload });
        await this.queue.save({ ...notice, attempts: notice.attempts + 1, sentAt: new Date().toISOString() });
        sent += 1;
      } catch (error) {
        await this.queue.save({ ...notice, attempts: notice.attempts + 1 });
      }
    }
    return sent;
  }
}
