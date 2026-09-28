import { ChevronDown, Search, X } from "lucide-react";
import { useMemo, useState } from "react";

import { Checkbox } from "~/components/ui/checkbox";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "~/components/ui/command";
import { cn } from "~/lib/utils";

export type ScopeWorkspace = { id: string; name: string };

export function WorkspaceScopeSelect({ id, label, workspaces, selectedIds, onChange }: {
  id: string;
  label: string;
  workspaces: ScopeWorkspace[];
  selectedIds: string[];
  onChange: (ids: string[]) => void;
}) {
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState("");
  const selected = new Set(selectedIds);
  const visible = filter.trim()
    ? workspaces.filter((workspace) => workspace.name.toLocaleLowerCase().includes(filter.trim().toLocaleLowerCase()))
    : workspaces;

  function toggle(workspaceId: string, checked: boolean) {
    onChange(checked ? [...selectedIds, workspaceId] : selectedIds.filter((id) => id !== workspaceId));
  }

  const summary = !workspaces.length
    ? "No workspaces"
    : selectedIds.length === workspaces.length
      ? `All ${workspaces.length} workspaces`
      : selectedIds.length === 0
        ? "No workspaces selected"
        : `${selectedIds.length} of ${workspaces.length} selected`;

  return (
    <div className="space-y-1.5">
      <p className="text-xs font-semibold text-zinc-600" id={`${id}-label`}>{label}</p>
      <button
        type="button"
        aria-labelledby={`${id}-label`}
        onClick={() => setOpen((value) => !value)}
        className="flex h-10 w-full items-center justify-between rounded-md border border-zinc-200 bg-white px-3 text-sm text-zinc-950 outline-none focus:border-teal-700 focus:ring-2 focus:ring-teal-100"
      >
        <span className="truncate">{summary}</span>
        <ChevronDown className={cn("size-4 shrink-0 text-zinc-400 transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <div className="space-y-2 border border-zinc-200 bg-white p-3 shadow-sm">
          <div className="flex items-center justify-between gap-2">
            <div className="flex gap-3 text-xs font-medium text-teal-700">
              <button type="button" onClick={() => onChange(workspaces.map((workspace) => workspace.id))}>Select all</button>
              <button type="button" onClick={() => onChange([])}>Clear</button>
            </div>
            <button type="button" onClick={() => setOpen(false)} className="text-xs font-medium text-zinc-500 hover:text-zinc-950">Done</button>
          </div>
          {workspaces.length > 8 && (
            <input
              value={filter}
              onChange={(event) => setFilter(event.target.value)}
              placeholder="Filter workspaces..."
              className="h-8 w-full rounded border border-zinc-200 px-2 text-xs outline-none focus:border-teal-700"
            />
          )}
          <div className="max-h-56 space-y-1 overflow-y-auto">
            {visible.map((workspace) => (
              <label key={workspace.id} className="flex items-center gap-2 rounded px-1.5 py-1 text-sm hover:bg-zinc-50">
                <Checkbox checked={selected.has(workspace.id)} onCheckedChange={(checked) => toggle(workspace.id, checked)} />
                <span className="min-w-0 truncate">{workspace.name}</span>
              </label>
            ))}
            {!visible.length && <p className="px-1.5 py-2 text-xs text-zinc-500">No workspaces match.</p>}
          </div>
        </div>
      )}
    </div>
  );
}

export type SearchEntry = {
  key: string;
  /** Composite text cmdk filters/searches against (name + model + workspace). */
  searchValue: string;
  primary: string;
  secondary: string;
  /** Selected-chip text when `primary` alone is ambiguous (e.g. the same table name in two models). */
  chipText?: string;
};

export function ObjectSearchSelect({ id, label, placeholder, entries, selectedKey, onChange, emptyText }: {
  id: string;
  label: string;
  placeholder: string;
  entries: SearchEntry[];
  selectedKey: string;
  onChange: (key: string) => void;
  emptyText: string;
}) {
  const [open, setOpen] = useState(false);
  const selectedEntry = entries.find((entry) => entry.key === selectedKey) ?? null;
  const visible = entries.slice(0, 200);
  const truncated = entries.length > visible.length;

  return (
    <div className="space-y-1.5">
      <p className="text-xs font-semibold text-zinc-600" id={`${id}-label`}>{label}</p>
      <button
        type="button"
        aria-labelledby={`${id}-label`}
        onClick={() => setOpen((value) => !value)}
        className="flex h-10 w-full items-center justify-between rounded-md border border-zinc-200 bg-white px-3 text-sm text-zinc-950 outline-none focus:border-teal-700 focus:ring-2 focus:ring-teal-100"
      >
        <span className="min-w-0 truncate text-left">{selectedEntry ? selectedEntry.primary : <span className="text-zinc-400">{placeholder}</span>}</span>
        <ChevronDown className={cn("size-4 shrink-0 text-zinc-400 transition-transform", open && "rotate-180")} />
      </button>
      {selectedEntry && <p className="truncate text-xs text-zinc-500">{selectedEntry.secondary}</p>}
      {open && (
        <div className="border border-zinc-200 bg-white shadow-sm">
          <Command>
            <CommandInput placeholder={placeholder} />
            <CommandList>
              <CommandEmpty>{entries.length ? "No matches." : emptyText}</CommandEmpty>
              {visible.map((entry) => (
                <CommandItem key={entry.key} value={entry.searchValue} onSelect={() => { onChange(entry.key); setOpen(false); }}>
                  <span className="flex min-w-0 flex-col">
                    <span className="truncate">{entry.primary}</span>
                    <span className="truncate text-xs text-zinc-500">{entry.secondary}</span>
                  </span>
                </CommandItem>
              ))}
              {truncated && <p className="px-3 py-2 text-xs text-zinc-500">Showing first 200 matches — refine your search.</p>}
            </CommandList>
          </Command>
        </div>
      )}
    </div>
  );
}

export type SearchGroup = {
  id: string;
  heading: string;
  /** Short tag shown on a selected entry's chip, e.g. "Semantic" or "Database". */
  chipLabel: string;
  entries: SearchEntry[];
};

const GROUP_RESULT_LIMIT = 100;

/**
 * One search box over several labelled result groups, selecting any number of
 * entries. It filters the full entry list itself (so a match past the first
 * page is still found) and shows the top matches of each group.
 */
export function MultiObjectSearch({ id, label, placeholder, groups, selectedKeys, onChange, emptyText }: {
  id: string;
  label: string;
  placeholder: string;
  groups: SearchGroup[];
  selectedKeys: string[];
  onChange: (keys: string[]) => void;
  emptyText: string;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const selected = new Set(selectedKeys);
  const entryByKey = useMemo(
    () => new Map(groups.flatMap((group) => group.entries.map((entry) => [entry.key, { entry, chipLabel: group.chipLabel }] as const))),
    [groups],
  );
  const needle = query.trim().toLocaleLowerCase();
  const tokens = needle.split(/\s+/).filter(Boolean);
  const results = groups.map((group) => {
    const matches = tokens.length
      ? group.entries
        .filter((entry) => {
          const haystack = entry.searchValue.toLocaleLowerCase();
          return tokens.every((token) => haystack.includes(token));
        })
        // Rank before the cap so a name match never hides behind model/workspace matches.
        .map((entry, order) => ({ entry, order, rank: matchRank(entry.primary.toLocaleLowerCase(), needle) }))
        .sort((a, b) => a.rank - b.rank || a.order - b.order)
        .map(({ entry }) => entry)
      : group.entries;
    return { ...group, total: matches.length, visible: matches.slice(0, GROUP_RESULT_LIMIT) };
  });
  const entryCount = groups.reduce((count, group) => count + group.entries.length, 0);
  const matchCount = results.reduce((count, group) => count + group.total, 0);
  const selectedEntries = selectedKeys.flatMap((key) => {
    const found = entryByKey.get(key);
    return found ? [{ key, ...found }] : [];
  });

  function toggle(key: string) {
    onChange(selected.has(key) ? selectedKeys.filter((selectedKey) => selectedKey !== key) : [...selectedKeys, key]);
  }

  return (
    <div className="space-y-2">
      <p className="text-xs font-semibold text-zinc-600" id={`${id}-label`}>{label}</p>
      <button
        type="button"
        aria-labelledby={`${id}-label`}
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className="flex h-10 w-full items-center justify-between gap-2 rounded-md border border-zinc-200 bg-white px-3 text-sm text-zinc-950 outline-none focus:border-teal-700 focus:ring-2 focus:ring-teal-100"
      >
        <span className="flex min-w-0 items-center gap-2">
          <Search className="size-4 shrink-0 text-zinc-400" />
          <span className="truncate">
            {selectedKeys.length ? `${selectedKeys.length} selected` : <span className="text-zinc-400">{placeholder}</span>}
          </span>
        </span>
        <ChevronDown className={cn("size-4 shrink-0 text-zinc-400 transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <div className="border border-zinc-200 bg-white shadow-sm">
          <Command shouldFilter={false}>
            <CommandInput value={query} onValueChange={setQuery} placeholder={placeholder} aria-label={placeholder} autoFocus />
            <CommandList className="max-h-96">
              {!entryCount && <CommandEmpty>{emptyText}</CommandEmpty>}
              {/* Every group keeps its own column, even with no matches, so the separation stays visible. */}
              {entryCount > 0 && <div className="grid md:grid-cols-2 md:divide-x md:divide-zinc-200">
              {results.map((group) => (
                <CommandGroup key={group.id} heading={`${group.heading} (${group.total})`} className="min-w-0">
                  {!group.total && <p className="px-2 py-3 text-xs text-zinc-500">{tokens.length ? "No matches." : "None indexed."}</p>}
                  {group.visible.map((entry) => {
                    const checked = selected.has(entry.key);
                    return (
                      <CommandItem key={entry.key} value={entry.key} data-checked={checked} onSelect={() => toggle(entry.key)}>
                        <span className="flex min-w-0 flex-col">
                          <span className="truncate">{entry.primary}</span>
                          <span className="truncate text-xs text-zinc-500">{entry.secondary}</span>
                        </span>
                        {checked && <span className="sr-only">(selected)</span>}
                      </CommandItem>
                    );
                  })}
                  {group.total > group.visible.length && (
                    <p className="px-2 py-1.5 text-xs text-zinc-500">Showing {group.visible.length} of {group.total} — refine your search.</p>
                  )}
                </CommandGroup>
              ))}
              </div>}
            </CommandList>
          </Command>
          <div className="flex items-center justify-between gap-2 border-t border-zinc-200 px-3 py-2 text-xs">
            <span className="text-zinc-500">{selectedKeys.length} selected</span>
            <div className="flex gap-3 font-medium">
              <button type="button" className="text-teal-700 disabled:text-zinc-400" disabled={!selectedKeys.length} onClick={() => onChange([])}>Clear</button>
              <button type="button" className="text-zinc-500 hover:text-zinc-950" onClick={() => setOpen(false)}>Done</button>
            </div>
          </div>
        </div>
      )}
      {selectedEntries.length > 0 && (
        <ul className="flex flex-wrap gap-1.5" aria-label={`Selected ${label.toLowerCase()}`}>
          {selectedEntries.map(({ key, entry, chipLabel }) => (
            <li key={key} className="flex max-w-full items-center gap-1.5 rounded-md border border-fabric/25 bg-accent py-1 pr-1 pl-2 text-xs text-accent-foreground">
              <span className="shrink-0 font-semibold uppercase opacity-70">{chipLabel}</span>
              <span className="min-w-0 truncate" title={`${entry.primary} — ${entry.secondary}`}>{entry.chipText ?? entry.primary}</span>
              <button type="button" aria-label={`Remove ${entry.chipText ?? entry.primary}`} onClick={() => toggle(key)} className="rounded p-0.5 hover:bg-fabric/15">
                <X className="size-3" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** 0 exact name, 1 name prefix, 2 a name segment starts with it, 3 name contains it, 4 matched only on other text. */
function matchRank(name: string, needle: string) {
  if (name === needle) return 0;
  if (name.startsWith(needle)) return 1;
  if (name.split(/[\s._\[\]()-]+/).some((part) => part.startsWith(needle))) return 2;
  if (name.includes(needle)) return 3;
  return 4;
}
