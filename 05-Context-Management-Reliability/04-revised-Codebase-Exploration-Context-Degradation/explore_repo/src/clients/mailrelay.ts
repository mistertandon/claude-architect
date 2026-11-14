/** One email as the Postwick API takes it. */
export interface OutgoingMail {
  to: string;
  template: string;
  variables: Record<string, string>;
}

const POSTWICK_URL = "https://send.postwick.example/api/messages";

/** Sends transactional emails through the Postwick email API. */
export class MailRelay {
  constructor(private readonly apiKey: string, private readonly sender = "orders@lumenhome.example") {}

  /** Sends one email; returns Postwick's message id. Throws when Postwick answers with an error. */
  async send(mail: OutgoingMail): Promise<string> {
    const response = await fetch(POSTWICK_URL, {
      method: "POST",
      headers: { "x-api-key": this.apiKey, "content-type": "application/json" },
      body: JSON.stringify({ from: this.sender, ...mail }),
    });
    if (!response.ok) {
      throw new Error(`Postwick refused the message: status ${response.status}`);
    }
    const body = (await response.json()) as { messageId: string };
    return body.messageId;
  }
}
