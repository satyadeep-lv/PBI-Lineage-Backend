import * as React from "react"
import { Search } from "lucide-react"
import { Input } from "~/components/ui/input"
import { cn } from "~/lib/utils"

interface TableSearchHeaderProps {
  searchTerm: string
  onSearchChange: (value: string) => void
  placeholder?: string
  className?: string
}

export function TableSearchHeader({
  searchTerm,
  onSearchChange,
  placeholder = "Search semantic tables or database tables...",
  className,
}: TableSearchHeaderProps) {
  return (
    <div className={cn("w-full mb-3", className)}>
      {/* Full-width grey search input bar only */}
      <div className="relative w-full">
        <Search className="absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground/70 pointer-events-none" />
        <Input
          type="text"
          placeholder={placeholder}
          value={searchTerm}
          onChange={(e) => onSearchChange(e.target.value)}
          className="h-10 w-full rounded-2xl border border-border/80 bg-slate-100/70 pl-10 pr-4 text-xs font-normal text-foreground placeholder:text-muted-foreground/70 focus-visible:bg-surface focus-visible:ring-2 focus-visible:ring-ring/20 transition-all"
        />
      </div>
    </div>
  )
}