import type { Entry } from "./domain";

export const columnFields = {
  transaction: "effective_description",
  card: "card_label",
  type: "effective_entry_type",
  account: "account_name",
  category: "category_name",
  amount: "effective_amount",
} as const;
export type SortColumn = keyof typeof columnFields;
export type TableOptions = {
  card?: string;
  type?: string;
  direction?: string;
  min?: string;
  max?: string;
  sort?: { column: SortColumn; ascending: boolean } | null;
};
const cents = (value: string) => {
  const [whole, fraction = ""] = value.split(".");
  return BigInt(whole) * 100n + BigInt(fraction.padEnd(2, "0"));
};
export function amountFilterError(options: TableOptions) {
  for (const value of [options.min, options.max])
    if (value && !/^\d{1,18}(\.\d{1,2})?$/.test(value))
      return "Enter nonnegative amounts with up to two decimal places.";
  if (options.min && options.max && cents(options.min) > cents(options.max))
    return "Minimum amount must not exceed maximum amount.";
  return "";
}
export function applyColumnOptions(rows: Entry[], options: TableOptions) {
  const result = rows.filter((row) => {
    const amount =
      row.effective_amount === undefined ? row.amount : row.effective_amount;
    return (
      (!options.card ||
        row.card_label
          .toLowerCase()
          .includes(options.card.toLowerCase().trim())) &&
      (!options.type ||
        (row.effective_entry_type ?? row.entry_type) === options.type) &&
      (!options.direction ||
        (row.effective_direction === undefined
          ? row.direction
          : row.effective_direction) === options.direction) &&
      (!options.min ||
        (amount !== null && cents(amount) >= cents(options.min))) &&
      (!options.max || (amount !== null && cents(amount) <= cents(options.max)))
    );
  });
  const sort = options.sort;
  if (!sort) return result;
  return result.sort((a, b) => {
    const value = (row: Entry): string | null => {
      switch (sort.column) {
        case "transaction":
          return row.effective_description ?? row.description;
        case "card":
          return row.card_label;
        case "type":
          return row.effective_entry_type ?? row.entry_type;
        case "account":
          return row.account_name;
        case "category":
          return row.category_name;
        case "amount":
          return row.effective_amount === undefined
            ? row.amount
            : row.effective_amount;
      }
    };
    const first = value(a),
      second = value(b);
    if (first === null) return second === null ? 0 : 1;
    if (second === null) return -1;
    const compared =
      sort.column === "amount"
        ? cents(first) < cents(second)
          ? -1
          : cents(first) > cents(second)
            ? 1
            : 0
        : first.localeCompare(second);
    return compared * (sort.ascending ? 1 : -1);
  });
}
