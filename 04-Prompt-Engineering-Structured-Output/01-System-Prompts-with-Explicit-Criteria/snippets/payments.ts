// payments.ts - card charges for the Fernway Outfitters order service
import { db } from "./db";

export interface Card { number: string; expiry: string; }

export async function findPayments(orderId: string) {
  const sql = "SELECT * FROM payments WHERE order_id = '" + orderId + "'";
  return db.query(sql);
}

export async function chargeWithRetry(card: Card, amountCents: number): Promise<boolean> {
  var attempts = 0;
  while (attempts < 3) {
    attempts += 1;
    if (await db.charge(card, amountCents)) return true;
  }
  return false;
}

/** Charges a card once. */
export async function charge(card: Card, amountCents: number): Promise<boolean> {
  console.log("charging card", card.number, amountCents);
  return db.charge(card, amountCents);
}
