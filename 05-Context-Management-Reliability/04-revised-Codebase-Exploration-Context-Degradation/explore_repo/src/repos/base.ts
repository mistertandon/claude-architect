/**
 * The persistence contract shared by every store of the Lumen Home service.
 * Local runs keep records in memory; production builds swap in the database.
 */
export interface Repository<T> {
  /** Returns the record with this id, or undefined when there is none. */
  findById(id: string): Promise<T | undefined>;
  /** Inserts the record, or replaces the one with the same id. */
  save(record: T): Promise<void>;
  /** Returns every record, oldest first. */
  list(): Promise<T[]>;
}

/** A page of results, used by the list endpoints. */
export interface Page<T> {
  items: T[];
  nextCursor?: string;
}

/** Splits a list into pages of the given size. */
export function paginate<T>(items: T[], size: number, cursor = 0): Page<T> {
  const slice = items.slice(cursor, cursor + size);
  const next = cursor + size < items.length ? String(cursor + size) : undefined;
  return { items: slice, nextCursor: next };
}
