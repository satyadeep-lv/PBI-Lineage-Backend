import { useIsFetching, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BookOpen,
  BookOpenCheck,
  Check,
  CheckCircle2,
  ChevronDown,
  CircleAlert,
  Loader2,
  Menu,
  RefreshCw,
} from "lucide-react";
import { useId, useState } from "react";
import { Link, useLocation } from "react-router";

import { Badge } from "~/components/ui/badge";
import { Button } from "~/components/ui/button";
import { ThemeToggle } from "~/components/theme-toggle";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "~/components/ui/dropdown-menu";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "~/components/ui/sheet";
import { clearServerCache } from "~/lib/lineage-api";
import { cn } from "~/lib/utils";
import { isApiReferencePath } from "~/lib/workspace-routes";
import { useAppStore } from "~/stores/app-store";

const navigationItems = [
  { label: "Home", to: "/", match: (pathname: string) => pathname === "/" },
  {
    label: "Workspace",
    to: "/workspace/power-bi",
    match: (pathname: string) => pathname.startsWith("/workspace") && !isApiReferencePath(pathname),
  },
];

/** Reading material rather than working screens, grouped under "Documents". */
const documentItems = [
  {
    label: "Setup guide",
    description: "Configure Microsoft, the database, and backend",
    to: "/setup-guide",
    icon: BookOpenCheck,
    match: (pathname: string) => pathname.startsWith("/setup-guide"),
  },
  {
    label: "API reference",
    description: "Browse and run the backend's operations",
    to: "/workspace/api-docs",
    icon: BookOpen,
    match: isApiReferencePath,
  },
];

/** The underline grows out from the centre on hover and settles in the brand colour on the current page. */
const headerNavItemClass =
  "relative flex items-center px-3 text-sm font-medium text-muted-foreground outline-none transition-colors duration-300 ease-apple hover:text-foreground focus-visible:text-foreground after:absolute after:inset-x-3 after:bottom-0 after:h-0.5 after:origin-center after:scale-x-0 after:rounded-full after:bg-foreground/20 after:transition-transform after:duration-300 after:ease-apple hover:after:scale-x-100 focus-visible:after:scale-x-100 lg:px-4 lg:after:inset-x-4";
const headerNavItemActiveClass =
  "text-foreground after:scale-x-100 after:bg-fabric";

async function checkHealth(apiOrigin: string) {
  const response = await fetch(`${apiOrigin}/api/v1/health`, {
    credentials: "include",
  });

  if (!response.ok) {
    throw new Error(`Health check failed with HTTP ${response.status}`);
  }

  return response.json() as Promise<unknown>;
}

/**
 * Both layers cache for the session, so both have to be cleared together. The
 * backend caches provider reads per signed-in user, and the browser caches the
 * responses it already has — clearing only one means the other serves the
 * stale copy and the button appears to do nothing. Server cache first, then
 * reset the query cache so whatever is on screen refetches against fresh data.
 */
function RefreshDataButton() {
  const queryClient = useQueryClient();
  const apiOrigin = useAppStore((state) => state.apiOrigin);
  const fetching = useIsFetching();
  const [isClearing, setIsClearing] = useState(false);

  async function refresh() {
    setIsClearing(true);
    try {
      await clearServerCache(apiOrigin);
    } catch {
      // A failed cache drop must not strand the user on stale data: reset the
      // browser cache anyway and let the refetch surface the real error.
    } finally {
      setIsClearing(false);
      void queryClient.resetQueries();
    }
  }

  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={() => void refresh()}
      className="text-muted-foreground hover:bg-accent hover:text-accent-foreground"
      aria-label="Refresh data"
      title="Refresh data — drops the server-side and browser caches, then reloads what is on screen"
    >
      <RefreshCw className={cn("size-4", (isClearing || fetching > 0) && "animate-spin")} />
    </Button>
  );
}

export function AppHeader({ showHealth = true }: { showHealth?: boolean }) {
  const apiOrigin = useAppStore((state) => state.apiOrigin);
  const { pathname } = useLocation();
  const healthQuery = useQuery({
    queryKey: ["backend-health", apiOrigin],
    queryFn: () => checkHealth(apiOrigin),
    enabled: showHealth,
    refetchInterval: 15_000,
    retry: 1,
  });

  return (
    <header className="sticky top-0 z-40 border-b border-border/70 bg-surface/75 backdrop-blur-xl backdrop-saturate-150">
      <div className="mx-auto flex min-h-16 max-w-screen-2xl items-center justify-between gap-4 px-4 sm:px-6 lg:px-8">
        <Link to="/" className="flex min-w-0 items-center gap-3" aria-label="PBI Lineage Explorer home">
          {/* Transparent logo mark; the dark-theme copy swaps its navy strokes for light slate. */}
          <span className="flex size-9 shrink-0 items-center justify-center">
            <img src="/tab_logo.png" alt="" width={36} height={36} className="size-full object-contain dark:hidden" />
            <img src="/tab_logo-dark.png" alt="" width={36} height={36} className="hidden size-full object-contain dark:block" />
          </span>
          <span className="min-w-0">
            <span className="block truncate text-sm font-semibold text-foreground sm:text-base">
              PBI Lineage Explorer
            </span>
            <span className="hidden truncate text-xs text-muted-foreground sm:block">
              Analytics lineage and impact intelligence
            </span>
          </span>
        </Link>

        <div className="hidden min-w-0 items-stretch self-stretch lg:flex">
          <HeaderNavigation pathname={pathname} />
        </div>

        <div className="flex shrink-0 items-center gap-2">
          <RefreshDataButton />
          {showHealth ? <HealthBadge query={healthQuery} compact /> : null}
          <ThemeToggle />

          <Sheet>
            <SheetTrigger
              render={
                <Button
                  variant="ghost"
                  size="icon"
                  className="text-muted-foreground hover:bg-accent hover:text-accent-foreground lg:hidden"
                  aria-label="Open navigation menu"
                />
              }
            >
              <Menu className="size-5" />
            </SheetTrigger>
            <SheetContent side="right" className="w-[min(22rem,88vw)] border-border p-0">
              <SheetHeader className="border-b border-border px-5 py-5">
                <SheetTitle>Navigation</SheetTitle>
                <SheetDescription>Move between the workspace and the reference documents.</SheetDescription>
              </SheetHeader>
              <nav aria-label="Mobile navigation" className="flex flex-col px-3 py-3">
                {navigationItems.map((item) => (
                  <MobileNavigationLink key={item.to} item={item} active={item.match(pathname)} />
                ))}
                <p className="mt-4 mb-1 border-l-2 border-transparent px-4 text-[11px] font-semibold uppercase text-muted-foreground">
                  Documents
                </p>
                {documentItems.map((item) => (
                  <MobileNavigationLink key={item.to} item={item} active={item.match(pathname)} nested />
                ))}
              </nav>
              {showHealth ? (
                <div className="mt-auto border-t border-border p-5">
                  <p className="mb-2 text-xs font-medium text-muted-foreground">Backend connection</p>
                  <HealthBadge query={healthQuery} />
                </div>
              ) : null}
            </SheetContent>
          </Sheet>
        </div>
      </div>
    </header>
  );
}

function MobileNavigationLink({
  item,
  active,
  nested = false,
}: {
  item: { label: string; to: string };
  active: boolean;
  nested?: boolean;
}) {
  return (
    <Link
      to={item.to}
      aria-current={active ? "page" : undefined}
      className={cn(
        "border-l-2 py-3 text-sm font-medium transition-colors duration-200 ease-apple",
        nested ? "pr-4 pl-7" : "px-4",
        active
          ? "border-fabric bg-accent text-accent-foreground"
          : "border-transparent text-muted-foreground hover:bg-muted hover:text-foreground",
      )}
    >
      {item.label}
    </Link>
  );
}

function HeaderNavigation({ pathname }: { pathname: string }) {
  return (
    <nav aria-label="Primary navigation" className="flex items-stretch">
      {navigationItems.map((item) => {
        const active = item.match(pathname);
        return (
          <Link
            key={item.to}
            to={item.to}
            aria-current={active ? "page" : undefined}
            className={cn(headerNavItemClass, active && headerNavItemActiveClass)}
          >
            {item.label}
          </Link>
        );
      })}
      <DocumentsMenu pathname={pathname} />
    </nav>
  );
}

/**
 * Each item's accessible name stays exactly its label: the description is
 * hidden from the name and attached as the item's description instead.
 */
function DocumentsMenu({ pathname }: { pathname: string }) {
  const descriptionId = useId();
  const active = documentItems.some((item) => item.match(pathname));

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        className={cn(
          headerNavItemClass,
          "group cursor-pointer gap-1 data-popup-open:text-foreground data-popup-open:after:scale-x-100",
          active && headerNavItemActiveClass,
        )}
      >
        Documents
        <ChevronDown
          aria-hidden="true"
          className="size-3.5 transition-transform duration-300 ease-apple group-data-popup-open:rotate-180"
        />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" sideOffset={6} className="w-96 p-1.5">
        <DropdownMenuGroup>
          {documentItems.map((item, index) => {
            const current = item.match(pathname);
            return (
              <DropdownMenuItem
                key={item.to}
                render={<Link to={item.to} />}
                aria-current={current ? "page" : undefined}
                aria-describedby={`${descriptionId}-${index}`}
                className={cn(
                  "group/doc cursor-pointer items-start gap-3 px-2.5 py-2",
                  current && "bg-accent/50 text-accent-foreground",
                )}
              >
                <span
                  className={cn(
                    "flex size-8 shrink-0 items-center justify-center rounded-lg border transition-colors duration-300 ease-apple",
                    current
                      ? "border-fabric/30 bg-fabric/10 text-fabric"
                      : "border-border bg-subtle text-muted-foreground group-focus/doc:border-fabric/30 group-focus/doc:text-fabric",
                  )}
                >
                  <item.icon className="size-4" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block font-medium">{item.label}</span>
                  <span
                    id={`${descriptionId}-${index}`}
                    aria-hidden="true"
                    className="mt-0.5 block text-xs leading-snug text-muted-foreground"
                  >
                    {item.description}
                  </span>
                </span>
                {current ? <Check className="mt-2 size-4 text-fabric" /> : null}
              </DropdownMenuItem>
            );
          })}
        </DropdownMenuGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

type HealthQuery = {
  isSuccess: boolean;
  isLoading: boolean;
};

function HealthBadge({ query, compact = false }: { query: HealthQuery; compact?: boolean }) {
  const label = query.isSuccess ? "online" : query.isLoading ? "checking" : "offline";

  return (
    <Badge
      className={cn(
        "rounded-full border px-2.5 py-1 transition-colors duration-300 ease-apple",
        query.isSuccess
          ? "border-success/30 bg-success/10 text-success"
          : query.isLoading
            ? "border-warning/30 bg-warning/10 text-warning"
            : "border-error/30 bg-error/10 text-error",
      )}
    >
      {query.isSuccess ? (
        <CheckCircle2 className="mr-1 size-3" />
      ) : query.isLoading ? (
        <Loader2 className="mr-1 size-3 animate-spin" />
      ) : (
        <CircleAlert className="mr-1 size-3" />
      )}
      <span className={compact ? "hidden lg:inline" : undefined}>Backend </span>
      {label}
    </Badge>
  );
}
