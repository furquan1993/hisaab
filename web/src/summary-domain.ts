import type { Entry } from "./domain";
import { cents } from "./funding-domain";
import { reviewedValues } from "./review-domain";
import type { Label } from "./useLabels";

export type SpendBucket = {
  id: string;
  name: string;
  charges: bigint;
  credits: bigint;
  count: number;
};
export type CurrencySummary = SpendBucket & {
  cards: Map<string, SpendBucket>;
  categories: Map<string, SpendBucket>;
  accounts: Map<string, SpendBucket>;
};

export function summarizeSpend(rows: Entry[], labels: Label[] = []) {
  const currencies = new Map<string, CurrencySummary>();
  let payments = 0,
    incomplete = 0,
    review = 0,
    entries = 0;
  const labelNames = new Map(labels.map((label) => [label.id, label.name]));
  for (const row of rows) {
    if (!row.is_selected) continue;
    const values = reviewedValues(row);
    if (values.entry_type === "payment") {
      payments++;
      continue;
    }
    entries++;
    if (row.needs_review) review++;
    if (values.amount === null || !values.direction || !values.currency) {
      incomplete++;
      continue;
    }
    const currency = values.currency;
    let summary = currencies.get(currency);
    if (!summary) {
      summary = {
        id: currency,
        name: currency,
        charges: 0n,
        credits: 0n,
        count: 0,
        cards: new Map(),
        categories: new Map(),
        accounts: new Map(),
      };
      currencies.set(currency, summary);
    }
    const amount = cents(values.amount);
    const add = (bucket: SpendBucket) => {
      bucket[values.direction === "debit" ? "charges" : "credits"] += amount;
      bucket.count++;
    };
    add(summary);
    const groups: [Map<string, SpendBucket>, string, string][] = [
      [summary.cards, row.card_id ?? row.card_label, row.card_label],
      [
        summary.categories,
        row.category_id ?? "unassigned",
        (row.category_id && labelNames.get(row.category_id)) ||
          row.category_name ||
          "Unassigned",
      ],
      [
        summary.accounts,
        row.account_id ?? "unassigned",
        (row.account_id && labelNames.get(row.account_id)) ||
          row.account_name ||
          "Unassigned",
      ],
    ];
    for (const [buckets, id, name] of groups) {
      const bucket = buckets.get(id) ?? {
        id,
        name,
        charges: 0n,
        credits: 0n,
        count: 0,
      };
      add(bucket);
      buckets.set(id, bucket);
    }
  }
  return {
    currencies: [...currencies.values()].sort((a, b) =>
      a.id.localeCompare(b.id),
    ),
    payments,
    incomplete,
    review,
    entries,
  };
}

export function sortedBuckets(buckets: Map<string, SpendBucket>) {
  return [...buckets.values()].sort((a, b) => {
    const difference = b.charges - b.credits - (a.charges - a.credits);
    return difference > 0n
      ? 1
      : difference < 0n
        ? -1
        : a.name.localeCompare(b.name);
  });
}
