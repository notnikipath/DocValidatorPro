import React, { useEffect, useMemo, useState } from "react";

import { KpiCard } from "../components/KpiCard";
import { TaskBoard } from "../components/TaskBoard";

const gatewayUrl = import.meta.env.VITE_API_GATEWAY_URL || "http://localhost:8500";

const emptyDashboard = {
  summary: {
    documents_total: 0,
    verified: 0,
    needs_review: 0,
    rejected: 0,
    rules_total: 0,
    quality_tasks_open: 0,
    audit_events: 0,
  },
  analytics: {
    validation_accuracy: 0,
    error_recall: 0,
    processing_throughput_docs_per_hour: 0,
    target_validation_accuracy: 0.99,
    target_error_recall: 0.95,
    target_docs_per_hour: 1000,
  },
  quality: {
    open_tasks: 0,
    critical_open_tasks: 0,
    resolved_tasks: 0,
    feedback_items: 0,
  },
  open_tasks: { items: [] },
  notifications: { items: [] },
  risk_forecast: { items: [] },
};

const emptyRuleForm = {
  name: "Check total amount",
  description: "Amount should stay positive",
  document_types: "financial",
  rule_type: "format",
  target_field: "total_amount",
  pattern: "",
  min_value: "0",
  max_value: "",
  severity: "warning",
};

async function fetchOverview(actorRole) {
  const response = await fetch(`${gatewayUrl}/dashboard/overview?actor_role=${actorRole}`);
  if (!response.ok) {
    throw new Error(`Dashboard request failed: ${response.status}`);
  }
  return response.json();
}

async function fetchRules(actorRole = "analyst") {
  const response = await fetch(`${gatewayUrl}/rules?actor_role=${actorRole}&enabled_only=true`);
  if (!response.ok) {
    throw new Error(`Rules request failed: ${response.status}`);
  }
  return response.json();
}

export function DashboardPage() {
  const [theme, setTheme] = useState("light");
  const [actorRole, setActorRole] = useState("analyst");
  const [dashboard, setDashboard] = useState(emptyDashboard);
  const [rules, setRules] = useState([]);
  const [ruleForm, setRuleForm] = useState(emptyRuleForm);
  const [csvText, setCsvText] = useState(
    "name,document_type,rule_type,target_field,pattern,min_value,max_value,severity,description\nINN Rule,financial,format,counterparty_inn,,, ,critical,INN checksum",
  );
  const [selectedRisk, setSelectedRisk] = useState(null);
  const [status, setStatus] = useState("loading");
  const [error, setError] = useState(null);

  const loadAll = async () => {
    try {
      setStatus("loading");
      const [overview, rulesResponse] = await Promise.all([fetchOverview(actorRole), fetchRules(actorRole)]);
      setDashboard({ ...emptyDashboard, ...overview });
      setRules(rulesResponse.items || []);
      setError(null);
      setStatus("ready");
    } catch (err) {
      setStatus("failed");
      setError(err.message);
    }
  };

  useEffect(() => {
    loadAll();
  }, [actorRole]);

  const riskItems = dashboard.risk_forecast?.items || [];
  const openTasks = dashboard.open_tasks?.items || [];
  const notifications = dashboard.notifications?.items || [];

  const statusLabel = useMemo(() => {
    if (status === "loading") {
      return "refreshing";
    }
    if (status === "failed") {
      return "Service unavailable";
    }
    return "live";
  }, [status]);

  const createRule = async () => {
    const payload = {
      ...ruleForm,
      document_types: ruleForm.document_types
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean),
      min_value: ruleForm.min_value === "" ? null : Number(ruleForm.min_value),
      max_value: ruleForm.max_value === "" ? null : Number(ruleForm.max_value),
      actor_id: "UI-ADMIN",
      actor_role: "admin",
    };
    const response = await fetch(`${gatewayUrl}/rules`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      throw new Error(`Create rule failed: ${response.status}`);
    }
    await loadAll();
  };

  const importRulesFromCsv = async () => {
    const response = await fetch(`${gatewayUrl}/rules/import/csv`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        csv_text: csvText,
        actor_id: "UI-ADMIN",
        actor_role: "admin",
      }),
    });
    if (!response.ok) {
      throw new Error(`CSV import failed: ${response.status}`);
    }
    await loadAll();
  };

  return (
    <div className={`app theme-${theme}`}>
      <div className="background-orb orb-a" />
      <div className="background-orb orb-b" />

      <header className="hero">
        <div className="hero-copy">
          <p className="eyebrow">DocValidator Pro</p>
          <h1>Качество документов</h1>
          <p className="sub">
            Платформа отслеживает ошибки распознавания, подозрительные изменения, риск неуплаты и историю корректировок
            по финансовым, юридическим, кадровым, медицинским и техническим документам.
          </p>
          <div className="hero-badges">
            <span>ML риск-скоринг</span>
            <span>Semantic checks</span>
            <span>Webhook exports</span>
            <span>Rule versioning</span>
          </div>
        </div>

        <div className="hero-panel">
          <label>
            Role
            <select value={actorRole} onChange={(event) => setActorRole(event.target.value)}>
              <option value="analyst">analyst</option>
              <option value="auditor">auditor</option>
              <option value="admin">admin</option>
            </select>
          </label>
          <div className="hero-actions">
            <button onClick={loadAll}>Refresh dashboard</button>
            <button className="ghost" onClick={() => setTheme((current) => (current === "light" ? "dark" : "light"))}>
              Theme
            </button>
          </div>
          <p className="status-line" role="status" aria-live="polite">Status: {statusLabel}</p>
          <p className="status-line" role="status" aria-live="polite">Documents: {dashboard.summary?.documents_total || 0}</p>
        </div>
      </header>

      <section className="kpi-grid">
        <KpiCard
          title="Validation Accuracy"
          value={`${(Number(dashboard.analytics?.validation_accuracy || 0) * 100).toFixed(2)}%`}
          target={`Target ${(Number(dashboard.analytics?.target_validation_accuracy || 0.99) * 100).toFixed(0)}%`}
          ok={Number(dashboard.analytics?.validation_accuracy || 0) >= Number(dashboard.analytics?.target_validation_accuracy || 0.99)}
        />
        <KpiCard
          title="Error Recall"
          value={`${(Number(dashboard.analytics?.error_recall || 0) * 100).toFixed(2)}%`}
          target={`Target ${(Number(dashboard.analytics?.target_error_recall || 0.95) * 100).toFixed(0)}%`}
          ok={Number(dashboard.analytics?.error_recall || 0) >= Number(dashboard.analytics?.target_error_recall || 0.95)}
        />
        <KpiCard
          title="Throughput"
          value={`${Number(dashboard.analytics?.processing_throughput_docs_per_hour || 0).toFixed(0)} docs/h`}
          target={`Target ${dashboard.analytics?.target_docs_per_hour || 1000} docs/h`}
          ok={Number(dashboard.analytics?.processing_throughput_docs_per_hour || 0) >= Number(dashboard.analytics?.target_docs_per_hour || 1000)}
        />
        <KpiCard
          title="Open Tasks"
          value={`${dashboard.quality?.open_tasks || 0}`}
          target={`Critical ${dashboard.quality?.critical_open_tasks || 0}`}
          ok={Number(dashboard.quality?.critical_open_tasks || 0) === 0}
        />
      </section>

      {error ? <div className="error-banner" role="alert">{error}</div> : null}

      <section className="content-grid">
        <article className="panel panel-featured">
          <div className="panel-head compact">
            <div>
              <p className="section-kicker">Quality Queue</p>
              <h2>Задачи на ручную доработку</h2>
            </div>
            <span className="pill">{openTasks.length} open</span>
          </div>
          <TaskBoard tasks={openTasks} />
        </article>

        <article className="panel">
          <div className="panel-head compact">
            <div>
              <p className="section-kicker">Risk Forecast</p>
              <h2>Документы с повышенным риском</h2>
            </div>
            <span className="pill accent">{riskItems.length}</span>
          </div>
          <div className="stack-list">
            {riskItems.map((item) => (
              <button className="stack-item btn-link" key={item.document_id} onClick={() => setSelectedRisk(item)}>
                <div>
                  <p className="stack-title">{item.document_id}</p>
                  <p className="stack-sub">{item.counterparty}</p>
                </div>
                <span>{Math.round((item.risk + item.fraud) * 50)}%</span>
              </button>
            ))}
          </div>
          {selectedRisk ? (
            <div className="empty-board">
              <strong>Drill-down:</strong> {selectedRisk.document_id}
              <br />
              Period: {selectedRisk.period}
              <br />
              Amount: {selectedRisk.amount}
              <br />
              Risk: {(selectedRisk.risk * 100).toFixed(1)}%
              <br />
              Fraud: {(selectedRisk.fraud * 100).toFixed(1)}%
            </div>
          ) : null}
        </article>

        <article className="panel">
          <div className="panel-head compact">
            <div>
              <p className="section-kicker">Notifications</p>
              <h2>Последние события</h2>
            </div>
            <span className="pill">{notifications.length}</span>
          </div>
          <div className="stack-list">
            {notifications.map((item) => (
              <div className="stack-item" key={item.event_id}>
                <div>
                  <p className="stack-title">{item.subject}</p>
                  <p className="stack-sub">{item.body}</p>
                </div>
                <span>{item.severity}</span>
              </div>
            ))}
          </div>
        </article>

        <article className="panel panel-analytics">
          <div className="panel-head compact">
            <div>
              <p className="section-kicker">Rules Studio</p>
              <h2>Управление правилами валидации</h2>
            </div>
            <span className="pill accent">{rules.length} active rules</span>
          </div>
          <div className="rule-grid">
            <label>
              Name
              <input value={ruleForm.name} onChange={(event) => setRuleForm((prev) => ({ ...prev, name: event.target.value }))} />
            </label>
            <label>
              Rule Type
              <select
                value={ruleForm.rule_type}
                onChange={(event) => setRuleForm((prev) => ({ ...prev, rule_type: event.target.value }))}
              >
                <option value="format">format</option>
                <option value="logic">logic</option>
                <option value="semantic">semantic</option>
              </select>
            </label>
            <label>
              Document Type
              <input
                value={ruleForm.document_types}
                onChange={(event) => setRuleForm((prev) => ({ ...prev, document_types: event.target.value }))}
                placeholder="financial,legal"
              />
            </label>
            <label>
              Target Field
              <input
                value={ruleForm.target_field}
                onChange={(event) => setRuleForm((prev) => ({ ...prev, target_field: event.target.value }))}
              />
            </label>
            <label>
              Pattern
              <input value={ruleForm.pattern} onChange={(event) => setRuleForm((prev) => ({ ...prev, pattern: event.target.value }))} />
            </label>
            <label>
              Min Value
              <input
                value={ruleForm.min_value}
                onChange={(event) => setRuleForm((prev) => ({ ...prev, min_value: event.target.value }))}
              />
            </label>
            <label>
              Max Value
              <input
                value={ruleForm.max_value}
                onChange={(event) => setRuleForm((prev) => ({ ...prev, max_value: event.target.value }))}
              />
            </label>
            <label>
              Severity
              <select
                value={ruleForm.severity}
                onChange={(event) => setRuleForm((prev) => ({ ...prev, severity: event.target.value }))}
              >
                <option value="info">info</option>
                <option value="warning">warning</option>
                <option value="critical">critical</option>
              </select>
            </label>
            <label className="wide">
              Description
              <input
                value={ruleForm.description}
                onChange={(event) => setRuleForm((prev) => ({ ...prev, description: event.target.value }))}
              />
            </label>
            <div className="wide hero-actions">
              <button onClick={createRule}>Create rule</button>
            </div>
          </div>
          <label>
            CSV Import
            <textarea value={csvText} onChange={(event) => setCsvText(event.target.value)} rows={4} />
          </label>
          <div className="hero-actions">
            <button onClick={importRulesFromCsv}>Import CSV</button>
          </div>
          <div className="stack-list">
            {rules.slice(0, 8).map((rule) => (
              <div className="stack-item" key={rule.rule_id}>
                <div>
                  <p className="stack-title">{rule.name}</p>
                  <p className="stack-sub">
                    {rule.rule_type} • {rule.target_field} • v{rule.version}
                  </p>
                </div>
                <span>{rule.severity}</span>
              </div>
            ))}
          </div>
        </article>
      </section>
    </div>
  );
}
