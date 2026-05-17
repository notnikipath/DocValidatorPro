import React from "react";

export function TaskBoard({ tasks }) {
  if (!tasks?.length) {
    return <div className="empty-board">Нет открытых задач качества. Пайплайн отрабатывает стабильно.</div>;
  }

  return (
    <section className="route-lane">
      {tasks.map((task) => (
        <article className="route-stop" key={task.task_id}>
          <p className="lesson-type">{task.priority}</p>
          <h4>{task.title}</h4>
          <div className="lesson-meta">
            <span>{task.document_id}</span>
            <span>{task.status}</span>
          </div>
        </article>
      ))}
    </section>
  );
}
