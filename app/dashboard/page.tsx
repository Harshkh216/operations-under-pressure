"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { DashboardSummary, WorkItemListResponse } from "@/lib/types";
import { SummaryCards } from "@/components/summary-cards";
import { WorkItemTable } from "@/components/work-item-table";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Plus, Search } from "lucide-react";
import { useToast } from "@/hooks/use-toast";

export default function DashboardPage() {
  const router = useRouter();
  const { toast } = useToast();
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(true);
  const [data, setData] = useState<WorkItemListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [searchInput, setSearchInput] = useState("");

  const loadSummary = useCallback(async () => {
    setSummaryLoading(true);
    try {
      const s = await api.getDashboardSummary();
      setSummary(s);
    } catch {
      // non-critical
    } finally {
      setSummaryLoading(false);
    }
  }, []);

  const loadItems = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const d = await api.listWorkItems({ page, page_size: 20, search: search || undefined });
      setData(d);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to load work items";
      setError(msg);
      if (msg.includes("session") || msg.includes("401")) {
        router.replace("/login");
      }
    } finally {
      setLoading(false);
    }
  }, [page, search, router]);

  useEffect(() => {
    loadSummary();
  }, [loadSummary]);

  useEffect(() => {
    loadItems();
  }, [loadItems]);

  function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    setPage(1);
    setSearch(searchInput);
  }

  function handleCardClick(view: string) {
    if (view === "assigned_to_me") router.push("/dashboard/assigned");
    else if (view === "unassigned_urgent") router.push("/dashboard/urgent");
    else if (view === "awaiting_my_approval") router.push("/dashboard/approvals");
  }

  return (
    <div className="space-y-6">
      <SummaryCards summary={summary} loading={summaryLoading} onCardClick={handleCardClick} />

      <div className="space-y-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <h2 className="text-lg font-semibold">All Work Items</h2>
          <div className="flex gap-2">
            <form onSubmit={handleSearch} className="relative">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                placeholder="Search title or description..."
                className="w-64 pl-9"
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
              />
            </form>
            <Button
              onClick={() => router.push("/dashboard/work-items/new")}
              size="sm"
            >
              <Plus className="mr-1 h-4 w-4" />
              New Task
            </Button>
          </div>
        </div>

        <WorkItemTable
          data={data}
          loading={loading}
          error={error}
          onPageChange={setPage}
          emptyMessage="No work items match your search."
        />
      </div>
    </div>
  );
}
