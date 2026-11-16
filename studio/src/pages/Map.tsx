// The map of what depends on what (core/dependencies.py): the parts the settings name, the
// instances at work in them, the agents they run, the tools each may call, the systems those come
// from, and the models, each as far as whoever's signed in may see it. Choosing one says what it
// depends on and what depends on it, so whoever's about to change it, or approve a change to it,
// sees what the change reaches first. Its address keeps what's chosen, so it can be linked to.

import { useState } from "react";
import { get } from "../api";
import type * as gen from "../api.gen";
import { DependsMap, KIND_NAMES, KINDS, type MapNode, reaching } from "../DependsMap";
import { href } from "../router";
import { PageHead, plural, To, useLoad, Waiting } from "../ui";

const kindOf = (node: MapNode) => KIND_NAMES[node.kind]?.[0].toLowerCase() ?? node.kind;
/** How one thing depends on another, in the words the map gives it, about something named:
 * "may call it" about change_due_date is "may call change_due_date". */
const told = (says: string, name: string) =>
  says.replace(/\bits\b/g, `${name}'s`).replace(/\bit\b/g, name);

/** Things on the map, each a way to choose it there, in the order the map's columns go. */
function Things({ keys, nodes, pick, none }: { keys: string[]; nodes: Map<string, MapNode>; pick: (key: string) => void; none: string }) {
  const found = keys.map((k) => nodes.get(k)).filter((n): n is MapNode => Boolean(n))
    .sort((a, b) => KINDS.indexOf(a.kind as never) - KINDS.indexOf(b.kind as never) || a.name.localeCompare(b.name));
  if (!found.length) return <p className="note">{none}</p>;
  return (
    <ul className="plain">{found.map((n) => (
      <li key={n.key}>
        <button type="button" className="link" data-pick={n.key} onClick={() => pick(n.key)}>{n.name}</button>
        <span className="note"> {kindOf(n)}</span>
      </li>
    ))}</ul>
  );
}

export function MapPage({ at }: { at?: string }) {
  const { data, error } = useLoad(() => get<gen.DependsOn>("/studio/api/map"), []);
  const [chosen, setChosen] = useState<string | null>(at ?? null);
  const pick = (key: string) => {
    const next = key === chosen ? null : key;
    setChosen(next);
    history.replaceState(null, "", next ? `${href({ page: "map" })}?at=${encodeURIComponent(next)}` : href({ page: "map" }));
  };
  const nodes = new Map((data?.nodes ?? []).map((n) => [n.key, n]));
  const picked = chosen ? nodes.get(chosen) : undefined;
  const reach = picked && data ? reaching(data.edges, picked.key) : null;
  const says = picked && data ? data.edges.filter((e) => e.from === picked.key || e.to === picked.key) : [];
  return (
    <>
      <PageHead title="Map"
                about="What depends on what: the parts the settings name, the instances at work in them, the agents they run, the tools each may call, the systems those come from, and the models. Choose anything to see what it depends on and what depends on it, so you know what a change to it reaches." />
      {!data && <Waiting error={error} block />}
      {data && !data.nodes.length && (
        <p id="status" role="status" className="note">There's nothing here you may see yet: no agent you may know of.</p>
      )}
      {data && data.nodes.length > 0 && (
        <div className="split">
          <DependsMap nodes={data.nodes} edges={data.edges} chosen={picked?.key ?? null} pick={pick}
                      label="What depends on what" />
          <section className="card" id="chosen" aria-live="polite">
            {!picked && (
              <>
                <h2>Choose something</h2>
                <p className="note">
                  {KINDS.map((k) => [k, data.nodes.filter((n) => n.kind === k).length] as const).filter(([, n]) => n)
                    .map(([k, n]) => plural(n, KIND_NAMES[k][0].toLowerCase(), KIND_NAMES[k][1].toLowerCase())).join(", ")}{" "}
                  you may see. Choose one on the map to see what it depends on, and what depends on it.
                </p>
              </>
            )}
            {picked && reach && (
              <>
                <h2>{picked.name}</h2>
                <p className="note">{KIND_NAMES[picked.kind]?.[0] ?? picked.kind}{picked.about ? `: ${picked.about}` : ""}</p>
                {picked.at && <p><To go={picked.at}>Open its page</To></p>}
                {says.length > 0 && (
                  <ul className="plain" id="says">{says.map((e) => (
                    <li key={`${e.from}>${e.to}`}>
                      {e.from === picked.key ? `It ${told(e.says, nodes.get(e.to)?.name ?? e.to)}.`
                        : `${nodes.get(e.from)?.name ?? e.from} ${told(e.says, picked.name)}.`}
                    </li>
                  ))}</ul>
                )}
                <h3>What depends on it</h3>
                <p className="note">A change to it may change how these work.</p>
                <div id="depended-on-by">
                  <Things keys={reach.by} nodes={nodes} pick={pick} none="Nothing you may see depends on it." />
                </div>
                {reach.parts.length > 0 && (
                  <>
                    <h3>The parts it reaches</h3>
                    <p className="note">Where the instances that depend on it work, whose owners decide what they do there.</p>
                    <div id="parts-reached">
                      <Things keys={reach.parts} nodes={nodes} pick={pick} none="" />
                    </div>
                  </>
                )}
                <h3>What it depends on</h3>
                <div id="depends-on">
                  <Things keys={reach.on} nodes={nodes} pick={pick} none="Nothing on the map." />
                </div>
              </>
            )}
          </section>
        </div>
      )}
    </>
  );
}
