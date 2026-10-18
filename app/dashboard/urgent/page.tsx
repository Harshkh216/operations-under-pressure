"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { WorkItemListResponse } from "@/lib/types";
import { WorkItemTable } from "@/components/work-item-table";

export default function UrgentPage() {
  const router = useRouter();
  const [data, setData] = useState<WorkItemListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const d = await api.listWorkItems({ page, page_size: 20, view: "unassigned_urgent" });
      setData(d);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to load";
      setError(msg);
      if (msg.includes("session") || msg.includes("401")) router.replace("/login");
    } finally {
      setLoading(false);
    }
  }, [page, router]);

  useEffect(() => { load(); }, [load]);

  return (
    <WorkItemTable
      data={data}
      loading={loading}
      error={error}
      onPageChange={setPage}
      emptyMessage="No urgent unassigned tasks. The queue is clear."
    />
  );
}
