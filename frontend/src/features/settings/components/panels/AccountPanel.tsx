"use client";

import React, { useMemo, useState } from "react";
import { UserAvatar } from "@/shared/ui/UserAvatar";
import { Input } from "@/shared/ui/input";
import { Button } from "@/shared/ui/button";
import { Label } from "@/shared/ui/label";
import { Separator } from "@/shared/ui/separator";
import { useAuth } from "@/features/auth/hooks/useAuth";
import { toast } from "sonner";
import { LogOut, Save } from "lucide-react";

interface AccountPanelProps {
  onClose?: () => void;
}

export function AccountPanel({ onClose }: AccountPanelProps) {
  const { user, updateProfile, logout } = useAuth();
  const [avatarUrl, setAvatarUrl] = useState("");
  const [saving, setSaving] = useState(false);
  const canSave = useMemo(() => avatarUrl.trim().length > 0, [avatarUrl]);

  const handleSave = async () => {
    if (!canSave) return;
    setSaving(true);
    try {
      await updateProfile({ avatar_url: avatarUrl.trim() });
      toast.success("Profile picture updated");
      setAvatarUrl("");
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Failed to update profile picture";
      toast.error(message);
    } finally {
      setSaving(false);
    }
  };

  const handleLogout = async () => {
    try {
      await logout();
      onClose?.();
    } catch {
      // toast inside logout already
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold">Account</h2>
        <p className="text-sm text-muted-foreground">
          Manage your profile picture and sign out.
        </p>
      </div>
      <Separator />

      <div className="flex items-center gap-4">
        <UserAvatar user={user} size="xl" />
        <div>
          <div className="text-sm font-medium">Current picture</div>
          <div className="text-xs text-muted-foreground">
            Provided by your auth provider
          </div>
        </div>
      </div>

      <div className="grid gap-2 max-w-xl">
        <Label htmlFor="avatar-url">Profile picture URL</Label>
        <Input
          id="avatar-url"
          placeholder="https://…/image.png"
          value={avatarUrl}
          onChange={(e) => setAvatarUrl(e.target.value)}
          autoComplete="off"
        />
        <div className="flex gap-2">
          <Button onClick={handleSave} disabled={!canSave || saving}>
            {saving ? (
              <div className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
            ) : (
              <Save className="h-4 w-4 mr-2" />
            )}
            Save
          </Button>
          <Button variant="outline" onClick={() => setAvatarUrl("")}>
            Clear
          </Button>
        </div>
      </div>

      <Separator />

      <div>
        <Button variant="destructive" onClick={handleLogout} className="gap-2">
          <LogOut className="h-4 w-4" />
          Log out
        </Button>
      </div>
    </div>
  );
}
