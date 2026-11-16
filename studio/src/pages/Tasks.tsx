// Someone's own tasks, folded into the studio from their own page (core/tasks_api.py): the long
// tasks they asked their agents for, how each stands, what it's waiting on and what it has
// spent; and the tasks they asked to be done again and again. To answer one that needs them, or
// to change what it's for, they write to the agent in their chat with it. They stop any here,
// asked first, since it can't be undone.

import { useState } from "react";
import { get, type RepeatLine, send, type TaskLine, type TasksNow } from "../api";
import { Confirm } from "../design";
import { PageHead, useLoad, Waiting } from "../ui";

const shown = (value: unknown) => (typeof value === "string" ? value : JSON.stringify(value));

function Task({ task, cancel }: { task: TaskLine; cancel: (task: TaskLine) => void }) {
  return (
    <li data-task={task.task}>
      <p>{task.task}, with the {task.agent}: {task.status}, {task.progress}% done{task.parts ? `, ${task.parts}` : ""}</p>
      {task.withheld
        ? <p className="note">What it's for names records you may no longer see, so it isn't shown here.</p>
        : (
          <>
            <p>{task.what}</p>
            {task.plan && task.plan.length > 0 && (
              <ol>{task.plan.map((step, i) => <li key={i}>{step.content} ({step.status.replace("_", " ")})</li>)}</ol>
            )}
            {task.found !== undefined && task.found !== null && <p>What it found: {shown(task.found)}</p>}
            {task["so far"] && task["so far"].length > 0 && <p className="note">So far: {task["so far"].map(shown).join("; ")}</p>}
            {task.why && <p className="note">Why: {task.why}</p>}
            {task.said && <p className="note">It needed: {task.needed || "you"}. You said: {task.said}</p>}
          </>
        )}
      <p className="note">It has until {task["has until"]}, and has spent {task.spent}. Last changed on {task.updated}.</p>
      {!task.ended && (
        <Confirm label="Cancel" title={`Cancel ${task.task}?`}
                 about="It stops at its next step, with the parts of it still open, and keeps what it found so far. To change what it's for instead, write to the agent in your chat with it."
                 confirm="Cancel it" danger onConfirm={() => cancel(task)} />
      )}
    </li>
  );
}

function Repeat({ repeat, stop }: { repeat: RepeatLine; stop: (repeat: RepeatLine) => void }) {
  return (
    <li data-repeat={repeat.repeat}>
      <p>{repeat.repeat}, with the {repeat.agent}: {repeat.when}, {repeat.status}</p>
      {repeat.withheld
        ? <p className="note">What it's for names records you may no longer see, so it isn't shown here.</p>
        : <p>{repeat.what}</p>}
      {repeat["last task"] && <p className="note">Its last task: {repeat["last task"]}.</p>}
      {repeat.status !== "stopped" && (
        <Confirm label="Stop" title={`Stop ${repeat.repeat}?`}
                 about="It makes no more tasks. Its last task, if one's going, goes on."
                 confirm="Stop it" danger onConfirm={() => stop(repeat)} />
      )}
    </li>
  );
}

export function TasksPage() {
  const [status, setStatus] = useState<string>();
  const { data, error, reload } = useLoad(() => get<TasksNow>("/tasks/api"), []);
  const end = async (name: string, said: string) => {
    try {
      await send("POST", `/tasks/api/${encodeURIComponent(name)}/cancel`);
      await reload();  // it says so with what it did in sight
      setStatus(`${said} ${name}.`);
    } catch (e) {
      setStatus((e as Error).message);
    }
  };
  return (
    <>
      <PageHead title="Your tasks"
                about="The long tasks you asked your agents for: how each stands, what it's waiting on, and what it has spent. To answer one that needs you, or to change what it's for, write to the agent in your chat with it. Stop any here." />
      <p id="status" role="status" className="note">
        {status ?? (data && data.tasks.length === 0 ? "No tasks yet. Ask an agent for one in your chat with it." : "")}
      </p>
      {!data && <Waiting error={error} />}
      {data && (
        <>
          <section className="card">
            <ul id="tasks" className="plain">
              {data.tasks.map((task) => <Task key={task.task} task={task} cancel={(t) => end(t.task, "Cancelled")} />)}
            </ul>
          </section>
          <section className="card">
            <h2>Again and again</h2>
            <p className="note">The tasks you asked to be done again and again: each time one comes round, it's a task of its own, above. Stopping one leaves its last task to go on.</p>
            <ul id="repeats" className="plain">
              {data.repeats.map((repeat) => <Repeat key={repeat.repeat} repeat={repeat} stop={(r) => end(r.repeat, "Stopped")} />)}
              {data.repeats.length === 0 && <li><p className="note">None. Ask an agent to do a task every week, say, in your chat with it.</p></li>}
            </ul>
          </section>
        </>
      )}
    </>
  );
}
