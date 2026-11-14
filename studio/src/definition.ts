// An agent's definition, agent.yaml, as the studio's forms read and change it. Each change is
// made to the document itself, so the file keeps its comments and layout as its author, or its
// template, wrote them: someone can start an agent here and finish it in an editor.

import { Document, isMap, isScalar, isSeq, parseDocument, type YAMLMap, type YAMLSeq } from "yaml";

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

/** A test case, as an agent's suite runs it on its model (tests/test_agents.py): what's said to
 * it, as whom, and at each step what it must use. */
export type Step = { say: string; uses?: string[] };
export type Case = { name: string; as: string; steps: Step[] };

export const CASES = "tests/tried.yaml";  // where the test pane keeps the cases it's given
const ABOUT = " Test cases kept from the sandbox's test pane: what was said to the agent, as whom, and\n"
  + " what it must use. Add what it must say, or never say, as the agent's other cases do.";

/** Test cases, as a file of them, with one more. One with the same name is refused. */
export function withCase(text: string, testCase: Case): string {
  const doc = text.trim() ? parseDocument(text) : new Document([]);
  if (doc.errors.length) throw new Error(`${CASES} doesn't read as YAML as it is: put it right under Files first`);
  if (!text.trim()) doc.commentBefore = ABOUT;
  const cases = doc.contents;
  if (!isSeq(cases)) throw new Error(`${CASES} isn't a list of test cases`);
  if (cases.items.some((item) => isMap(item) && item.get("name") === testCase.name)) {
    throw new Error(`it has a test case called ${testCase.name} already`);
  }
  const node = doc.createNode(testCase) as YAMLMap;
  const steps = node.get("steps", true);
  for (const step of isSeq(steps) ? steps.items : []) {
    const uses = isMap(step) ? step.get("uses", true) : null;
    if (isSeq(uses)) uses.flow = true;  // [a, b], as people write them
  }
  cases.flow = false;
  cases.add(node);
  return doc.toString({ flowCollectionPadding: false });
}
