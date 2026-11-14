// An agent's definition, agent.yaml, as the studio's forms read and change it. Each change is
// made to the document itself, so the file keeps its comments and layout as its author, or its
// template, wrote them: someone can start an agent here and finish it in an editor.

import { type Document, isMap, isScalar, isSeq, parseDocument, type YAMLMap, type YAMLSeq } from "yaml";

export type Spec = {
  works_for: string;
  does: string;
  model: string;
  autonomy: { start: number; max: number };
  tools: Record<string, string[]>;  // by group, as its author grouped them
};

/** What the forms show of a definition, or null if it doesn't read as YAML. */
export function read(text: string): Spec | null {
  const doc = parseDocument(text);
  if (doc.errors.length) return null;
  const found = (doc.toJS() ?? {}) as Record<string, unknown>;
  const autonomy = (found.autonomy ?? {}) as Record<string, unknown>;
  const tools = (found.tools ?? {}) as Record<string, unknown>;
  return {
    works_for: String(found.works_for ?? ""),
    does: String(found.does ?? ""),
    model: String(found.model ?? ""),
    autonomy: { start: Number(autonomy.start ?? 0), max: Number(autonomy.max ?? 0) },
    tools: Object.fromEntries(Object.entries(tools).map(([group, names]) =>
      [group, Array.isArray(names) ? names.map(String) : []])),
  };
}

export class Unreadable extends Error {
  constructor() {
    super("agent.yaml doesn't read as YAML as it is: put it right under Files first");
  }
}

function edited(text: string, change: (doc: Document) => void): string {
  const doc = parseDocument(text);
  if (doc.errors.length) throw new Unreadable();
  change(doc);
  return doc.toString({ flowCollectionPadding: false });  // [a, b], as people write them
}

/** With a value set in place, so its comment, and its style, such as a folded block, stay. */
export function withValue(text: string, path: string[], value: string | number): string {
  return edited(text, (doc) => {
    const node = doc.getIn(path, true);
    if (isScalar(node)) node.value = value;
    else doc.setIn(path, value);
  });
}

/** With a tool or without it. One it gains goes into the first group whose tools all do what it
 * does, as `kind` says, or else a new group named for that. */
export function withTool(text: string, tool: string, on: boolean, kind: string,
                         kindOf: (name: string) => string): string {
  return edited(text, (doc) => {
    if (!isMap(doc.get("tools", true))) doc.set("tools", doc.createNode({}));
    const groups = doc.get("tools", true) as YAMLMap;
    for (const [i, pair] of groups.items.entries()) {
      const names = pair.value;
      if (!isSeq(names)) continue;
      const at = names.items.findIndex((item) => isScalar(item) && item.value === tool);
      if (at < 0) continue;
      if (!on) {
        names.items.splice(at, 1);
        if (names.items.length === 0) groups.items.splice(i, 1);
      }
      return;
    }
    if (!on) return;
    const beside = groups.items.find((pair) => isSeq(pair.value) && pair.value.items.length > 0
      && pair.value.items.every((item) => isScalar(item) && kindOf(String(item.value)) === kind));
    if (beside && isSeq(beside.value)) {
      beside.value.add(doc.createNode(tool));
      return;
    }
    const named = groups.get(kind, true);
    if (isSeq(named)) {
      named.add(doc.createNode(tool));
      return;
    }
    const fresh = doc.createNode([tool]) as YAMLSeq;
    fresh.flow = true;
    groups.set(kind, fresh);
  });
}
