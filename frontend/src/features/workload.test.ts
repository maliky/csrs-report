import {
  estimatedWorkDaysFromInput,
  normalizeWorkloadInputValue,
  workloadInputFromDays,
  workloadInputMin,
  workloadInputStep,
} from "./workload";

test("convertit les jours et heures sans perdre les fractions", () => {
  expect(workloadInputFromDays("2.5", "hours")).toBe("20");
  expect(estimatedWorkDaysFromInput("13", "hours")).toBe("1.625");
  expect(estimatedWorkDaysFromInput("1.5", "hours")).toBe("0.1875");
});

test("applique les minimums et précisions validés", () => {
  expect(workloadInputMin("days")).toBe(0.5);
  expect(workloadInputStep("days")).toBe(0.25);
  expect(workloadInputMin("hours")).toBe(1);
  expect(workloadInputStep("hours")).toBe(0.5);
  expect(normalizeWorkloadInputValue("1.2", "days")).toBe("1.25");
  expect(normalizeWorkloadInputValue("4.4", "hours")).toBe("4.5");
});
