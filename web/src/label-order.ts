const nameOrder = new Intl.Collator("en", {
  numeric: true,
  sensitivity: "base",
});

export const compareLabelNames = nameOrder.compare;
