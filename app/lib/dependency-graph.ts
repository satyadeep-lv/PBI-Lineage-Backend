import type { LineageGraph, LineageGraphEdge, LineageGraphNode, LineageNodeKind } from "~/components/workspace/lineage/lineage-types";

export type DaxReference = { object_type: string; table_name?: string | null; object_name: string; qualified_name: string; expression?: string | null };
export type DaxDependency = { source: DaxReference; target: DaxReference; reference_text: string };

export type ClosureHop = {
  reference: DaxReference;
  depth: number;
  referenceText: string;
  /** Key of the node that discovered this hop (a seed, or a closer node in the same direction). */
  viaKey: string;
};

export type DependencyClosure = {
  seeds: DaxReference[];
  upstream: ClosureHop[];
  downstream: ClosureHop[];
};

export function canonicalType(value: string): string {
  const type = value.trim().toLocaleLowerCase().replace(/[\s-]+/g, "_");
  if (type.includes("calculated_column")) return "calculated_column";
  if (type.includes("calculated_table")) return "calculated_table";
  if (type.includes("measure")) return "measure";
  if (type.includes("column")) return "column";
  if (type.includes("table")) return "table";
  return type;
}

export function referenceKey(reference: DaxReference): string {
  const table = (reference.table_name ?? "").trim().toLocaleLowerCase();
  const name = reference.object_name.trim().toLocaleLowerCase();
  return `${canonicalType(reference.object_type)}|${table}|${name}`;
}

export function referenceLabel(reference: DaxReference): string {
  return reference.qualified_name || (reference.table_name ? `${reference.table_name}[${reference.object_name}]` : reference.object_name);
}

export function objectTypeToKind(objectType: string): LineageNodeKind {
  switch (canonicalType(objectType)) {
    case "measure":
      return "measure";
    case "calculated_column":
      return "calculated-column";
    case "calculated_table":
      return "calculated-table";
    case "table":
      return "table";
    default:
      return "column";
  }
}

/**
 * Multi-source BFS over a flat DAX dependency edge list. `source` on an edge is always the
 * upstream/referenced object and `target` is the downstream object whose expression references
 * it (this matches the backend's /lineage/dax/analyze contract) — so "upstream" walks backward
 * along edges (target -> source) and "downstream" walks forward (source -> target).
 */
export function computeDependencyClosure(
  dependencies: DaxDependency[],
  seeds: DaxReference[],
  options: { maxDepth?: number } = {},
): DependencyClosure {
  const maxDepth = options.maxDepth ?? Number.POSITIVE_INFINITY;
  const seedKeys = seeds.map(referenceKey);

  function walk(currentSideOf: (dependency: DaxDependency) => DaxReference, nextSideOf: (dependency: DaxDependency) => DaxReference): ClosureHop[] {
    const visited = new Set(seedKeys);
    const hops: ClosureHop[] = [];
    let frontier = [...seedKeys];
    let depth = 0;

    while (frontier.length && depth < maxDepth) {
      depth += 1;
      const matches = dependencies.filter((dependency) => frontier.includes(referenceKey(currentSideOf(dependency))));
      const discovered = new Map<string, DaxDependency>();
      matches.forEach((dependency) => {
        const key = referenceKey(nextSideOf(dependency));
        if (!visited.has(key) && !discovered.has(key)) discovered.set(key, dependency);
      });
      discovered.forEach((dependency, key) => {
        visited.add(key);
        hops.push({
          reference: nextSideOf(dependency),
          depth,
          referenceText: dependency.reference_text,
          viaKey: referenceKey(currentSideOf(dependency)),
        });
      });
      frontier = [...discovered.keys()];
    }
    return hops;
  }

  const upstream = walk((dependency) => dependency.target, (dependency) => dependency.source);
  const downstream = walk((dependency) => dependency.source, (dependency) => dependency.target);

  // A multi-seed selection (e.g. "whole table") can have direct edges BETWEEN two seeds (one
  // seed's measure reads another seed's column). The BFS above starts every seed already
  // "visited", so those edges never surface as hops even though they are real, one-hop impact —
  // add them explicitly so seed-to-seed relationships still appear as rows/nodes.
  if (seedKeys.length > 1) {
    const seedKeySet = new Set(seedKeys);
    const seedByKey = new Map(seeds.map((seed) => [referenceKey(seed), seed]));
    const seenDownstream = new Set(downstream.map((hop) => referenceKey(hop.reference)));
    const seenUpstream = new Set(upstream.map((hop) => referenceKey(hop.reference)));
    dependencies.forEach((dependency) => {
      const sourceKey = referenceKey(dependency.source);
      const targetKey = referenceKey(dependency.target);
      if (sourceKey === targetKey || !seedKeySet.has(sourceKey) || !seedKeySet.has(targetKey)) return;
      if (!seenDownstream.has(targetKey)) {
        downstream.push({ reference: seedByKey.get(targetKey)!, depth: 1, referenceText: dependency.reference_text, viaKey: sourceKey });
        seenDownstream.add(targetKey);
      }
      if (!seenUpstream.has(sourceKey)) {
        upstream.push({ reference: seedByKey.get(sourceKey)!, depth: 1, referenceText: dependency.reference_text, viaKey: targetKey });
        seenUpstream.add(sourceKey);
      }
    });
  }

  return { seeds, upstream, downstream };
}

/**
 * Converts a closure into a diagram-ready graph. `dependencies` should be the same flat edge
 * list the closure was computed from — it is re-scanned so that every real edge between two
 * VISIBLE nodes is included (not just the edges BFS happened to discover a node through), which
 * matters whenever two seeds are directly related (e.g. a multi-seed "whole table" selection) or
 * two nodes converge on a shared downstream/upstream target ("diamond" dependencies).
 */
export function closureToLineageGraph(closure: DependencyClosure, dependencies: DaxDependency[]): LineageGraph {
  const nodes = new Map<string, LineageGraphNode>();

  function addNode(reference: DaxReference, isFocal: boolean) {
    const key = referenceKey(reference);
    const existing = nodes.get(key);
    nodes.set(key, {
      id: key,
      kind: objectTypeToKind(reference.object_type),
      label: referenceLabel(reference),
      isFocal: Boolean(existing?.isFocal || isFocal),
    });
    return key;
  }

  closure.seeds.forEach((seed) => addNode(seed, true));
  closure.upstream.forEach((hop) => addNode(hop.reference, false));
  closure.downstream.forEach((hop) => addNode(hop.reference, false));

  const nodeKeys = new Set(nodes.keys());
  const edges = new Map<string, LineageGraphEdge>();
  dependencies.forEach((dependency) => {
    const sourceKey = referenceKey(dependency.source);
    const targetKey = referenceKey(dependency.target);
    if (!nodeKeys.has(sourceKey) || !nodeKeys.has(targetKey)) return;
    const id = `${sourceKey}=>${targetKey}`;
    if (!edges.has(id)) edges.set(id, { id, source: sourceKey, target: targetKey, label: dependency.reference_text });
  });

  return { nodes: [...nodes.values()], edges: [...edges.values()] };
}
