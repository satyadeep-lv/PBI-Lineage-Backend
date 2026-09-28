import type { Route } from "./+types/setup-guide";
import { AppFooter } from "~/components/app-footer";
import { AppHeader } from "~/components/app-header";
import { SetupGuide } from "~/components/setup-guide/setup-guide";

export function meta({}: Route.MetaArgs) {
  return [
    { title: "Setup Guide | PBI Lineage Explorer" },
    {
      name: "description",
      content: "Create the Microsoft Entra app, service principal, and read-only Snowflake role PBI Lineage Explorer needs to access workspaces and lineage.",
    },
  ];
}

export default function SetupGuideRoute() {
  return (
    <div className="flex min-h-screen flex-col bg-app text-foreground">
      <AppHeader />
      <SetupGuide />
      <AppFooter />
    </div>
  );
}
