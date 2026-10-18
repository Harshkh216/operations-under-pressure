"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ListTodo, AlertTriangle, CheckCircle, FolderOpen } from "lucide-react";
import type { DashboardSummary } from "@/lib/types";
import { cn } from "@/lib/utils";

interface SummaryCardsProps {
  summary: DashboardSummary | null;
  loading: boolean;
  onCardClick?: (view: string) => void;
}

const cards = [
  { key: "assigned_to_me", label: "Assigned to Me", icon: ListTodo, view: "assigned_to_me", color: "text-blue-600" },
  { key: "unassigned_urgent", label: "Unassigned Urgent", icon: AlertTriangle, view: "unassigned_urgent", color: "text-red-600" },
  { key: "awaiting_my_approval", label: "Awaiting Approval", icon: CheckCircle, view: "awaiting_my_approval", color: "text-amber-600" },
  { key: "total_visible", label: "Total Visible", icon: FolderOpen, view: null, color: "text-slate-600" },
] as const;

export function SummaryCards({ summary, loading, onCardClick }: SummaryCardsProps) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {cards.map((card) => (
        <Card
          key={card.key}
          className={cn(
            "transition-shadow hover:shadow-md",
            onCardClick && card.view && "cursor-pointer",
          )}
          onClick={() => onCardClick && card.view && onCardClick(card.view)}
        >
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              {card.label}
            </CardTitle>
            <card.icon className={cn("h-4 w-4", card.color)} />
          </CardHeader>
          <CardContent>
            {loading ? (
              <Skeleton className="h-8 w-16" />
            ) : (
              <div className="text-2xl font-bold">
                {summary ? summary[card.key as keyof typeof summary] : 0}
              </div>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
