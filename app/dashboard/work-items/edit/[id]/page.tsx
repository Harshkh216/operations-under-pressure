"use client";

import { useState, useEffect } from "react";
import { useRouter, useParams } from "next/navigation";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Loader2, ArrowLeft } from "lucide-react";
import type { Priority, WorkItem } from "@/lib/types";

export default function WorkItemFormPage() {
  const router = useRouter();
  const params = useParams();
  const { user } = useAuth();
  const editId = params?.id ? Number(params.id) : null;
  const isEdit = editId !== null;

  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [priority, setPriority] = useState<Priority>("medium");
  const [teamId, setTeamId] = useState<number | null>(null);
  const [assigneeId, setAssigneeId] = useState<string>("none");
  const [dueAt, setDueAt] = useState("");
  const [version, setVersion] = useState(1);
  const [loading, setLoading] = useState(isEdit);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const managerTeams = user?.memberships.filter((m) => m.role === "manager") || [];

  useEffect(() => {
    if (!isEdit) {
      if (managerTeams.length > 0) setTeamId(managerTeams[0].team_id);
      return;
    }
    // Load existing item for editing.
    (async () => {
      try {
        const wi = await api.getWorkItem(editId!);
        setTitle(wi.title);
        setDescription(wi.description);
        setPriority(wi.priority);
        setTeamId(wi.team_id);
        setAssigneeId(wi.assignee_id ? String(wi.assignee_id) : "none");
        setDueAt(wi.due_at ? wi.due_at.slice(0, 10) : "");
        setVersion(wi.version);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load");
      } finally {
        setLoading(false);
      }
    })();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editId]);

  // Only managers can create. If not a manager and not editing, redirect.
  useEffect(() => {
    if (!isEdit && managerTeams.length === 0 && user) {
      setError("Only managers can create work items.");
    }
  }, [isEdit, managerTeams.length, user]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      if (isEdit && editId !== null) {
        await api.updateWorkItem(editId, {
          title,
          description,
          priority,
          due_at: dueAt ? new Date(dueAt).toISOString() : null,
          assignee_id: assigneeId === "none" ? null : Number(assigneeId),
          version,
        });
        router.push(`/dashboard/work-items/${editId}`);
      } else if (teamId) {
        await api.createWorkItem({
          team_id: teamId,
          title,
          description,
          priority,
          due_at: dueAt ? new Date(dueAt).toISOString() : null,
          assignee_id: assigneeId === "none" ? null : Number(assigneeId),
        });
        router.push("/dashboard");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save");
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl space-y-4">
      <Button variant="ghost" size="sm" onClick={() => router.back()}>
        <ArrowLeft className="mr-1 h-4 w-4" />
        Back
      </Button>
      <Card>
        <CardHeader>
          <CardTitle>{isEdit ? "Edit Task" : "Create New Task"}</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            {error && (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
            <div className="space-y-2">
              <Label htmlFor="title">Title</Label>
              <Input
                id="title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                required
                maxLength={200}
                placeholder="Brief summary of the task"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="description">Description</Label>
              <Textarea
                id="description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={4}
                maxLength={4000}
                placeholder="Detailed description, context, and acceptance criteria"
              />
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label>Priority</Label>
                <Select value={priority} onValueChange={(v) => setPriority(v as Priority)}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="low">Low</SelectItem>
                    <SelectItem value="medium">Medium</SelectItem>
                    <SelectItem value="high">High</SelectItem>
                    <SelectItem value="urgent">Urgent</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="dueAt">Due Date</Label>
                <Input
                  id="dueAt"
                  type="date"
                  value={dueAt}
                  onChange={(e) => setDueAt(e.target.value)}
                />
              </div>
            </div>
            {!isEdit && (
              <div className="space-y-2">
                <Label>Team</Label>
                <Select
                  value={teamId ? String(teamId) : undefined}
                  onValueChange={(v) => setTeamId(Number(v))}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select team" />
                  </SelectTrigger>
                  <SelectContent>
                    {managerTeams.map((m) => (
                      <SelectItem key={m.team_id} value={String(m.team_id)}>
                        {m.team_name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
            {isEdit && (
              <div className="space-y-2">
                <Label>Assignee</Label>
                <Select value={assigneeId} onValueChange={setAssigneeId}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">Unassigned</SelectItem>
                    <SelectItem value={String(user?.id)}>Myself ({user?.full_name})</SelectItem>
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">
                  Reassigning is limited to managers. The assignee must be a team member.
                </p>
              </div>
            )}
            <div className="flex justify-end gap-2 pt-2">
              <Button type="button" variant="outline" onClick={() => router.back()}>
                Cancel
              </Button>
              <Button type="submit" disabled={submitting}>
                {submitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                {isEdit ? "Save Changes" : "Create Task"}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
