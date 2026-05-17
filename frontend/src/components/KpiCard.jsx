import React from "react";

export function KpiCard({ title, value, target, ok }) {
  return (
    <article className="kpi-card">
      <p className="kpi-title">{title}</p>
      <p className="kpi-value">{value}</p>
      <p className={`kpi-target ${ok ? "ok" : "warn"}`}>{target}</p>
    </article>
  );
}