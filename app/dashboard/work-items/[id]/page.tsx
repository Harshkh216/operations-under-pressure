"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter, useParams } from "next/navigation";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Separator } from "@/components/ui/separator";
import {
  ArrowLeft,
  Loader2,
  Edit,
  Hand,
  Send,
  CheckCircle2,
  XCircle,
  Ban,
  PlayCircle,
  StopCircle,
  CircleDot,
  Check,
} from "lucide-react";
import type {
  ActivityEvent,
  Comment,
  TransitionAction,
  WorkItem,
} from "@/lib/types";
import {
  formatDate,
  formatDateTime,
  priorityColor,
  priorityLabel,
  statusColor,
  statusLabel,
  timeAgo,
} from "@/lib/badges";
import { cn } from "@/lib/utils";

export default function WorkItemDetailPage() {
  const router = useRouter();
  const params = useParams();
  const { user } = useAuth();
  const workItemId = Number(params?.id);

  const [item, setItem] = useState<WorkItem | null>(null);
  const [comments, setComments] = useState<Comment[]>([]);
  const [activity, setActivity] = useState<ActivityEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [commentBody, setCommentBody] = useState("");
  const [commentSubmitting, setCommentSubmitting] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [wi, c, a] = await Promise.all([
        api.getWorkItem(workItemId),
        api.getComments(workItemId),
        api.getActivity(workItemId),
      ]);
      setItem(wi);
      setComments(c);
      setActivity(a);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to load";
      setError(msg);
      if (msg.includes("session") || msg.includes("401")) router.replace("/login");
    } finally {
      setLoading(false);
    }
  }, [workItemId, router]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleTransition(action: TransitionAction) {
    if (!item) return;
    setActionLoading(true);
    setActionError(null);
    try {
      const updated = await api.transition(item.id, action, item.version);
      setItem(updated);
      // Reload activity + comments to show the new state.
      const [a] = await Promise.all([api.getActivity(item.id)]);
      setActivity(a);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Action failed");
      // If 409, reload to get the current version.
      if (err instanceof Error && err.message.includes("modified")) {
        await load();
      }
    } finally {
      setActionLoading(false);
    }
  }

  async function handleAddComment(e: React.FormEvent) {
    e.preventDefault();
    if (!commentBody.trim()) return;
    setCommentSubmitting(true);
    try {
      const c = await api.addComment(workItemId, commentBody.trim());
      setComments((prev) => [...prev, c]);
      setCommentBody("");
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to add comment");
    } finally {
      setCommentSubmitting(false);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error && !item) {
    return (
      <div className="space-y-4">
        <Button variant="ghost" size="sm" onClick={() => router.back()}>
          <ArrowLeft className="mr-1 h-4 w-4" />
          Back
        </Button>
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      </div>
    );
  }

  if (!item) return null;

  const isManager = user?.memberships.some(
    (m) => m.team_id === item.team_id && m.role === "manager",
  );
  const isAssignee = item.assignee_id === user?.id;
  const isContributor = user?.memberships.some(
    (m) => m.team_id === item.team_id && m.role === "contributor",
  );

  // Available transitions based on status and role.
  const transitions: { action: TransitionAction; label: string; icon: typeof Hand; confirm?: boolean }[] = [];
  if (item.status === "open" && isContributor) {
    transitions.push({ action: "claim", label: "Claim", icon: Hand });
  }
  if (item.status === "in_progress" && isAssignee) {
    transitions.push({ action: "start_review", label: "Submit for Review", icon: Send, confirm: true });
    transitions.push({ action: "block", label: "Mark Blocked", icon: StopCircle, confirm: true });
    transitions.push({ action: "release", label: "Release", icon: CircleDot, confirm: true });
  }
  if (item.status === "blocked" && isAssignee) {
    transitions.push({ action: "unblock", label: "Unblock", icon: PlayCircle });
  }
  if (item.status === "in_review" && isManager) {
    transitions.push({ action: "approve", label: "Approve", icon: CheckCircle2, confirm: true });
    transitions.push({ action: "reject", label: "Reject", icon: XCircle, confirm: true });
  }
  if (item.status === "approved" && isManager) {
    transitions.push({ action: "complete", label: "Complete", icon: Check, confirm: true });
  }
  if (["open", "in_progress", "blocked", "in_review"].includes(item.status) && isManager) {
    transitions.push({ action: "cancel", label: "Cancel", icon: Ban, confirm: true });
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <Button variant="ghost" size="sm" onClick={() => router.back()}>
          <ArrowLeft className="mr-1 h-4 w-4" />
          Back
        </Button>
        {isManager && (
          <Button variant="outline" size="sm" onClick={() => router.push(`/dashboard/work-items/edit/${item.id}`)}>
            <Edit className="mr-1 h-4 w-4" />
            Edit
          </Button>
        )}
      </div>

      {actionError && (
        <Alert variant="destructive">
          <AlertDescription>{actionError}</AlertDescription>
        </Alert>
      )}

      {/* Header */}
      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="outline" className={cn("border", statusColor[item.status])}>
            {statusLabel[item.status]}
          </Badge>
          <Badge variant="outline" className={cn("border", priorityColor[item.priority])}>
            {priorityLabel[item.priority]}
          </Badge>
          <span className="text-xs text-muted-foreground">
            v{item.version} · Created {formatDate(item.created_at)}
          </span>
        </div>
        <h1 className="text-2xl font-bold">{item.title}</h1>
        <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm text-muted-foreground">
          <span>Assignee: <strong className="text-foreground">{item.assignee_name || "Unassigned"}</strong></span>
          <span>Due: <strong className="text-foreground">{formatDate(item.due_at)}</strong></span>
          {item.team_name && <span>Team: <strong className="text-foreground">{item.team_name}</strong></span>}
        </div>
      </div>

      {/* Action buttons */}
      {transitions.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {transitions.map((t) => (
            <ActionButton
              key={t.action}
              label={t.label}
              icon={t.icon}
              confirm={t.confirm}
              loading={actionLoading}
              onConfirm={() => handleTransition(t.action)}
            />
          ))}
        </div>
      )}

      <Separator />

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Description + Comments */}
        <div className="space-y-6 lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Description</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="whitespace-pre-wrap text-sm">{item.description || "No description provided."}</p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Comments ({comments.length})</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {comments.length === 0 ? (
                <p className="text-sm text-muted-foreground">No comments yet.</p>
              ) : (
                <div className="space-y-3">
                  {comments.map((c) => (
                    <div key={c.id} className="rounded-md border p-3">
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-medium">{c.author_name || "Unknown"}</span>
                        <span className="text-xs text-muted-foreground">{timeAgo(c.created_at)}</span>
                      </div>
                      <p className="mt-1 whitespace-pre-wrap text-sm">{c.body}</p>
                    </div>
                  ))}
                </div>
              )}
              <form onSubmit={handleAddComment} className="space-y-2">
                <Textarea
                  placeholder="Add a comment..."
                  value={commentBody}
                  onChange={(e) => setCommentBody(e.target.value)}
                  rows={2}
                  maxLength={2000}
                />
                <div className="flex justify-end">
                  <Button type="submit" size="sm" disabled={commentSubmitting || !commentBody.trim()}>
                    {commentSubmitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                    Post Comment
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>
        </div>

        {/* Activity timeline */}
        <div>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Activity Timeline</CardTitle>
            </CardHeader>
            <CardContent>
              {activity.length === 0 ? (
                <p className="text-sm text-muted-foreground">No activity recorded.</p>
              ) : (
                <ol className="relative space-y-4 border-l pl-4">
                  {activity.map((a) => (
                    <li key={a.id} className="relative">
                      <span className="absolute -left-[21px] top-1 h-2.5 w-2.5 rounded-full border-2 border-background bg-primary" />
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium">{a.actor_name || "Unknown"}</span>
                        <Badge variant="secondary" className="text-xs">{a.action}</Badge>
                      </div>
                      <p className="text-xs text-muted-foreground">{a.detail}</p>
                      <p className="text-xs text-muted-foreground">{formatDateTime(a.created_at)}</p>
                    </li>
                  ))}
                </ol>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

function ActionButton({
  label,
  icon: Icon,
  confirm,
  loading,
  onConfirm,
}: {
  label: string;
  icon: typeof Hand;
  confirm?: boolean;
  loading: boolean;
  onConfirm: () => void;
}) {
  if (confirm) {
    return (
      <AlertDialog>
        <AlertDialogTrigger asChild>
          <Button variant="outline" size="sm" disabled={loading}>
            <Icon className="mr-1 h-4 w-4" />
            {label}
          </Button>
        </AlertDialogTrigger>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Confirm: {label}</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to perform this action? This will change the work item status.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={onConfirm}>Confirm</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    );
  }
  return (
    <Button variant="outline" size="sm" disabled={loading} onClick={onConfirm}>
      <Icon className="mr-1 h-4 w-4" />
      {label}
    </Button>
  );
}
