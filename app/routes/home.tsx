import {
  ArrowDown,
  ArrowRight,
  BarChart3,
  Database,
  GitBranch,
  PlayCircle,
  TableProperties,
} from "lucide-react";
import { Link } from "react-router";

import type { Route } from "./+types/home";
import { AppFooter } from "~/components/app-footer";
import { AppHeader } from "~/components/app-header";
import { Reveal } from "~/components/reveal";
import { Button } from "~/components/ui/button";

export function meta({}: Route.MetaArgs) {
  return [
    { title: "PBI Lineage Explorer" },
    {
      name: "description",
      content: "Trace Power BI assets from source data through semantic logic to downstream report impact.",
    },
  ];
}

const evidenceLayers = [
  { icon: Database, label: "Source systems", detail: "Databases and schemas" },
  { icon: TableProperties, label: "Semantic layer", detail: "Models, fields, and DAX" },
  { icon: BarChart3, label: "Power BI assets", detail: "Reports, pages, and visuals" },
  { icon: GitBranch, label: "Change impact", detail: "Dependencies and affected assets" },
];

const investigationPrompts = [
  ["Trace a value", "Follow report evidence through measures, semantic objects, and verified source structures."],
  ["Assess a change", "Inspect downstream table, measure, report, page, and visual dependencies before release."],
  ["Review access and coverage", "Keep workspace context, asset ownership, scan coverage, and warnings in one workflow."],
];

/**
 * The captions burned into /how-to-use-*.gif, in order. Regenerate the
 * animation with scripts/walkthrough/ (capture.cjs, then compose.py) whenever
 * these or the screens they show change.
 */
const walkthroughSteps = [
  "Connect Power BI & Fabric",
  "Connect your database (optional)",
  "See everything your account can access",
  "Open any report in Explorer",
  "Trace report lineage end to end",
  "Check which reports, models, and measures use a table",
  "Follow a measure to every visual",
  "Ask Power AI about anything you can see",
  "Setup guide and API reference live under Documents",
];

/** Pixel size of both walkthrough GIFs and their posters. */
const WALKTHROUGH_WIDTH = 1280;
const WALKTHROUGH_HEIGHT = 800;

/** Hero lines rise in one after another on load, the way apple.com opens a page. */
const HERO_RISE = "motion-safe:animate-rise";
const heroDelay = (step: number) => ({ animationDelay: `${step * 90}ms` });

export default function Home() {
  return (
    <div className="min-h-screen bg-app text-foreground">
      <AppHeader showHealth={false} />

      <main className="power-ai-aware">
        <section className="relative overflow-hidden border-b border-border bg-app">
          {/* A soft brand-coloured glow behind the headline. */}
          <div
            aria-hidden="true"
            className="pointer-events-none absolute inset-x-0 top-0 h-[560px] bg-[radial-gradient(55%_65%_at_50%_0%,color-mix(in_srgb,var(--fabric-primary)_16%,transparent),transparent)]"
          />
          <div className="relative mx-auto max-w-screen-2xl px-4 pt-14 pb-16 sm:px-6 sm:pt-20 sm:pb-20 lg:px-8 lg:pt-24">
            <div className="mx-auto max-w-4xl text-center">
              <p className={`${HERO_RISE} text-xs font-semibold tracking-[0.14em] text-fabric uppercase`} style={heroDelay(0)}>
                Power BI lineage and impact analysis
              </p>
              <h1
                className={`${HERO_RISE} mt-4 text-5xl leading-[1.05] font-semibold tracking-tight text-foreground sm:text-6xl lg:text-7xl`}
                style={heroDelay(1)}
              >
                PBI Lineage Explorer
              </h1>
              <p
                className={`${HERO_RISE} mx-auto mt-5 max-w-2xl text-lg leading-8 text-muted-foreground sm:text-xl sm:leading-9`}
                style={heroDelay(2)}
              >
                Trace how source data becomes semantic logic, reports, and business decisions. Investigate dependencies and change impact without piecing evidence together by hand.
              </p>
              <div className={`${HERO_RISE} mt-9 flex flex-wrap justify-center gap-3`} style={heroDelay(3)}>
                <Button nativeButton={false} size="lg" render={<Link to="/workspace/explorer" />}>
                  Start exploring
                  <ArrowRight data-icon="inline-end" className="size-4" />
                </Button>
                <Button nativeButton={false} size="lg" variant="outline-brand" render={<Link to="/setup-guide" />}>
                  Setup guide
                </Button>
              </div>
            </div>

            <Reveal
              as="figure"
              variant="zoom"
              className="mt-12 overflow-hidden rounded-2xl border border-border bg-surface shadow-[0_40px_120px_-48px_color-mix(in_srgb,var(--fabric-primary)_45%,transparent)] sm:mt-16"
            >
              <div className="flex items-center justify-between gap-4 border-b border-border px-4 py-3 sm:px-5">
                <div className="flex min-w-0 items-center gap-2 text-sm font-medium text-foreground">
                  <PlayCircle className="size-4 shrink-0 text-fabric" />
                  <span className="truncate">How PBI Lineage Explorer works</span>
                </div>
                <span className="hidden text-xs text-muted-foreground sm:block">
                  Animated walkthrough · {walkthroughSteps.length} steps
                </span>
              </div>
              {/* One animation per theme; each falls back to its still poster under reduced motion. */}
              <div className="aspect-[1280/800] bg-subtle">
                <picture className="block size-full dark:hidden">
                  <source media="(prefers-reduced-motion: reduce)" srcSet="/how-to-use-light.png" />
                  <img
                    src="/how-to-use-light.gif"
                    alt="Animated walkthrough of PBI Lineage Explorer"
                    width={WALKTHROUGH_WIDTH}
                    height={WALKTHROUGH_HEIGHT}
                    loading="lazy"
                    decoding="async"
                    className="size-full object-contain"
                  />
                </picture>
                <picture className="hidden size-full dark:block">
                  <source media="(prefers-reduced-motion: reduce)" srcSet="/how-to-use-dark.png" />
                  <img
                    src="/how-to-use-dark.gif"
                    alt="Animated walkthrough of PBI Lineage Explorer"
                    width={WALKTHROUGH_WIDTH}
                    height={WALKTHROUGH_HEIGHT}
                    loading="lazy"
                    decoding="async"
                    className="size-full object-contain"
                  />
                </picture>
              </div>
              <figcaption className="border-t border-border px-4 py-4 sm:px-5">
                <ol className="grid gap-x-6 gap-y-2 sm:grid-cols-2 lg:grid-cols-3">
                  {walkthroughSteps.map((step, index) => (
                    <li key={step} className="flex min-w-0 gap-2.5 text-xs leading-5 text-muted-foreground">
                      <span aria-hidden="true" className="shrink-0 font-mono text-fabric">
                        {String(index + 1).padStart(2, "0")}
                      </span>
                      <span>{step}</span>
                    </li>
                  ))}
                </ol>
              </figcaption>
            </Reveal>
          </div>
        </section>

        <section className="border-b border-border bg-surface" aria-labelledby="evidence-path-heading">
          <div className="mx-auto max-w-screen-2xl px-4 py-16 sm:px-6 sm:py-20 lg:px-8">
            <Reveal className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
              <div>
                <p className="text-xs font-semibold tracking-[0.14em] text-fabric uppercase">Connected evidence path</p>
                <h2 id="evidence-path-heading" className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
                  From source systems to change impact
                </h2>
              </div>
              <p className="max-w-xl text-sm leading-6 text-muted-foreground sm:text-base sm:leading-7">
                Each view keeps the workspace, report, semantic model, and physical source context visible as the investigation moves downstream.
              </p>
            </Reveal>

            <div className="mt-10 grid gap-2 md:grid-cols-[1fr_auto_1fr_auto_1fr_auto_1fr] md:items-stretch">
              {evidenceLayers.map((layer, index) => (
                <div key={layer.label} className="contents">
                  <Reveal delay={index * 90} className="h-full">
                    <article className="group h-full rounded-2xl border border-border bg-subtle px-5 py-5 transition-[translate,box-shadow,border-color,background-color] duration-500 ease-apple hover:-translate-y-1 hover:border-fabric/30 hover:bg-surface hover:shadow-[0_24px_60px_-28px_rgb(0_0_0/0.28)]">
                      <div className="flex items-center gap-3">
                        <span className="flex size-10 shrink-0 items-center justify-center rounded-xl border border-fabric/20 bg-surface text-fabric transition-colors duration-500 ease-apple group-hover:border-fabric group-hover:bg-fabric group-hover:text-primary-foreground">
                          <layer.icon className="size-4" />
                        </span>
                        <div className="min-w-0">
                          <h3 className="text-sm font-semibold">{layer.label}</h3>
                          <p className="mt-0.5 text-xs text-muted-foreground">{layer.detail}</p>
                        </div>
                      </div>
                    </article>
                  </Reveal>
                  {index < evidenceLayers.length - 1 ? (
                    <div className="flex items-center justify-center py-1 text-fabric/70" aria-hidden="true">
                      <ArrowDown className="size-4 md:hidden" />
                      <ArrowRight className="hidden size-4 md:block" />
                    </div>
                  ) : null}
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="bg-app">
          <div className="mx-auto grid max-w-screen-2xl gap-0 px-4 py-16 sm:px-6 sm:py-20 lg:grid-cols-3 lg:px-8">
            {investigationPrompts.map(([title, text], index) => (
              <Reveal
                key={title}
                as="article"
                delay={index * 110}
                className="border-b border-border py-6 last:border-b-0 lg:border-r lg:border-b-0 lg:px-8 lg:first:pl-0 lg:last:border-r-0"
              >
                <span className="font-mono text-xs text-fabric">0{index + 1}</span>
                <h2 className="mt-3 text-xl font-semibold tracking-tight">{title}</h2>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">{text}</p>
              </Reveal>
            ))}
          </div>
        </section>
      </main>

      <AppFooter />
    </div>
  );
}
