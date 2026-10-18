"use client";

import { useRouter } from "next/navigation";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { ChevronLeft, ChevronRight, Inbox } from "lucide-react";
import type { WorkItem, WorkItemListResponse } from "@/lib/types";
import { formatDate, priorityColor, priorityLabel, statusColor, statusLabel } from "@/lib/badges";
import { cn } from "@/lib/utils";

interface WorkItemTableProps {
  data: WorkItemListResponse | null;
  loading: boolean;
  error: string | null;
  onPageChange: (page: number) => void;
  emptyMessage?: string;
}

export function WorkItemTable({ data, loading, error, onPageChange, emptyMessage }: WorkItemTableProps) {
  const router = useRouter();

  if (error) {
    return (
      <div className="rounded-md border border-destructive/30 bg-destructive/5 p-6 text-center">
        <p className="text-sm text-destructive">{error}</p>
        <Button variant="outline" size="sm" className="mt-3" onClick={() => onPageChange(1)}>
          Retry
        </Button>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    );
  }

  if (!data || data.items.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center rounded-md border border-dashed py-16 text-center">
        <Inbox className="mb-3 h-10 w-10 text-muted-foreground/50" />
        <p className="text-sm text-muted-foreground">
          {emptyMessage || "No work items found."}
        </p>
      </div>
    );
  }

  const totalPages = Math.ceil(data.total / data.page_size);
  const hasPrev = data.page > 1;
  const hasNext = data.page < totalPages;

  return (
    <div className="space-y-4">
      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-[40%]">Title</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Priority</TableHead>
              <TableHead>Assignee</TableHead>
              <TableHead>Due</TableHead>
              <TableHead className="text-right">v</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.items.map((item) => (
              <TableRow
                key={item.id}
                className="cursor-pointer hover:bg-muted/50"
                onClick={() => router.push(`/dashboard/work-items/${item.id}`)}
              >
                <TableCell className="font-medium">
                  <div className="flex items-center gap-2">
                    <span className="truncate">{item.title}</span>
                  </div>
                </TableCell>
                <TableCell>
                  <Badge variant="outline" className={cn("border", statusColor[item.status])}>
                    {statusLabel[item.status]}
                  </Badge>
                </TableCell>
                <TableCell>
                  <Badge variant="outline" className={cn("border", priorityColor[item.priority])}>
                    {priorityLabel[item.priority]}
                  </Badge>
                </TableCell>
                <TableCell className="text-sm text-muted-foreground">
                  {item.assignee_name || "Unassigned"}
                </TableCell>
                <TableCell className="text-sm text-muted-foreground">
                  {formatDate(item.due_at)}
                </TableCell>
                <TableCell className="text-right text-xs text-muted-foreground">
                  v{item.version}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">
            Page {data.page} of {totalPages} · {data.total} items
          </p>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={!hasPrev}
              onClick={() => onPageChange(data.page - 1)}
            >
              <ChevronLeft className="mr-1 h-4 w-4" />
              Prev
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={!hasNext}
              onClick={() => onPageChange(data.page + 1)}
            >
              Next
              <ChevronRight className="ml-1 h-4 w-4" />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
