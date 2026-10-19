import { expect, it } from "vitest";
import { demoEntries } from "./demo";
import { amountFilterError, applyColumnOptions } from "./entry-table";

it("compares exact amounts without rounding and leaves unknowns last in either direction", () => {
  const rows = [
    { ...demoEntries[0], id: "big", amount: "9007199254740993.01" },
    { ...demoEntries[0], id: "small", amount: "9007199254740993.00" },
    { ...demoEntries[0], id: "unknown", amount: null },
  ];
  expect(
    applyColumnOptions(rows, {
      sort: { column: "amount", ascending: true },
    }).map((r) => r.id),
  ).toEqual(["small", "big", "unknown"]);
  expect(
    applyColumnOptions(rows, {
      sort: { column: "amount", ascending: false },
    }).map((r) => r.id),
  ).toEqual(["big", "small", "unknown"]);
  expect(rows[0].id).toBe("big");
});
it("combines card, reviewed type, direction and exact amount range", () => {
  const row = {
    ...demoEntries[0],
    card_label: "Travel card",
    amount: "10.00",
    effective_amount: "42.05",
    effective_entry_type: "refund",
    effective_direction: "credit" as const,
  };
  expect(
    applyColumnOptions([row], {
      card: "TRAVEL",
      type: "refund",
      direction: "credit",
      min: "42.05",
      max: "42.05",
    }),
  ).toEqual([row]);
  expect(applyColumnOptions([row], { max: "42.04" })).toEqual([]);
});
it("validates decimal precision and inverted bounds", () => {
  expect(amountFilterError({ min: "0", max: "999999999999999999.99" })).toBe(
    "",
  );
  for (const options of [
    { min: "1.001" },
    { min: "-1" },
    { max: "1e3" },
    { min: "2", max: "1.99" },
  ])
    expect(amountFilterError(options)).not.toBe("");
});
