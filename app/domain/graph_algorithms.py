from collections.abc import Iterator


def strongly_connected_components(
    adjacency: dict[str, set[str]],
) -> list[set[str]]:
    graph = {node: set(neighbors) for node, neighbors in adjacency.items()}
    for neighbors in adjacency.values():
        for neighbor in neighbors:
            graph.setdefault(neighbor, set())

    next_index = 0
    component_stack: list[str] = []
    on_stack: set[str] = set()
    indices: dict[str, int] = {}
    low_links: dict[str, int] = {}
    components: list[set[str]] = []

    def push(
        frames: list[tuple[str, Iterator[str], str | None]],
        node: str,
        parent: str | None,
    ) -> None:
        nonlocal next_index
        indices[node] = next_index
        low_links[node] = next_index
        next_index += 1
        component_stack.append(node)
        on_stack.add(node)
        frames.append((node, iter(graph[node]), parent))

    for root in graph:
        if root in indices:
            continue
        frames: list[tuple[str, Iterator[str], str | None]] = []
        push(frames, root, None)

        while frames:
            node, neighbors, parent = frames[-1]
            try:
                neighbor = next(neighbors)
            except StopIteration:
                frames.pop()
                if low_links[node] == indices[node]:
                    component: set[str] = set()
                    while component_stack:
                        member = component_stack.pop()
                        on_stack.remove(member)
                        component.add(member)
                        if member == node:
                            break
                    components.append(component)
                if parent is not None:
                    low_links[parent] = min(low_links[parent], low_links[node])
                continue

            if neighbor not in indices:
                push(frames, neighbor, node)
            elif neighbor in on_stack:
                low_links[node] = min(low_links[node], indices[neighbor])

    return components
