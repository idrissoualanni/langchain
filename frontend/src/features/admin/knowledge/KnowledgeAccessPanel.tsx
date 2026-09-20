// Knowledge Access Panel Component
import { useState, useEffect } from "react";
import { useToast } from "@/hooks/use-toast";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { GroupSelector } from "./GroupSelector";
import { UserSelector } from "./UserSelector";
import { apiRequest } from "@/api/request";

interface AccessRule {
  scope: string;
  target: string;
}

interface KnowledgeAccessPanelProps {
  knowledgeBaseId: string;
}

export function KnowledgeAccessPanel({ knowledgeBaseId }: KnowledgeAccessPanelProps) {
  const [scope, setScope] = useState<string>("private");
  const [selectedGroups, setSelectedGroups] = useState<string[]>([]);
  const [selectedUsers, setSelectedUsers] = useState<string[]>([]);
  const [isPublic, setIsPublic] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const { toast } = useToast();

  const loadAccess = async () => {
    try {
      const response = await apiRequest(`/api/admin/knowledge/${knowledgeBaseId}/access`);
      const data = await response.json();
      
      if (data.rules) {
        const publicRule = data.rules.find((r: AccessRule) => r.scope === 'public');
        const groupRules = data.rules.filter((r: AccessRule) => r.scope === 'group');
        const userRules = data.rules.filter((r: AccessRule) => r.scope === 'user');
        
        setIsPublic(!!publicRule);
        setSelectedGroups(groupRules.map((r: AccessRule) => r.target));
        setSelectedUsers(userRules.map((r: AccessRule) => r.target));
        
        if (publicRule) setScope('public');
        else if (groupRules.length > 0) setScope('group');
        else if (userRules.length > 0) setScope('user');
        else setScope('private');
      }
    } catch (error) {
      console.error("Failed to load access rules:", error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (knowledgeBaseId) {
      loadAccess();
    }
  }, [knowledgeBaseId]);

  const handleSave = async () => {
    setSaving(true);
    try {
      // Clear existing rules
      await apiRequest(`/api/admin/knowledge/${knowledgeBaseId}/access`, {
        method: 'DELETE',
      });

      // Add new rules based on scope
      if (isPublic || scope === 'public') {
        await apiRequest(`/api/admin/knowledge/${knowledgeBaseId}/access`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ scope: 'public', target: '' }),
        });
      }

      if (scope === 'group') {
        for (const groupId of selectedGroups) {
          await apiRequest(`/api/admin/knowledge/${knowledgeBaseId}/access`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ scope: 'group', target: groupId }),
          });
        }
      }

      if (scope === 'user') {
        for (const userId of selectedUsers) {
          await apiRequest(`/api/admin/knowledge/${knowledgeBaseId}/access`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ scope: 'user', target: userId }),
          });
        }
      }

      toast({ title: "Access rules updated successfully" });
      loadAccess();
    } catch (error) {
      toast({
        title: "Error updating access rules",
        description: error instanceof Error ? error.message : "Unknown error",
        variant: "destructive",
      });
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <div className="text-sm text-muted-foreground">Loading access rules...</div>;
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Knowledge Base Access Control</CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <Label htmlFor="public-access">Public Access</Label>
            <p className="text-sm text-muted-foreground">
              Allow all users to access this knowledge base
            </p>
          </div>
          <Switch
            id="public-access"
            checked={isPublic}
            onCheckedChange={setIsPublic}
          />
        </div>

        {!isPublic && (
          <>
            <div className="space-y-2">
              <Label>Access Scope</Label>
              <Select value={scope} onValueChange={setScope}>
                <SelectTrigger>
                  <SelectValue placeholder="Select access scope" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="private">Private (Owner only)</SelectItem>
                  <SelectItem value="group">Group-based</SelectItem>
                  <SelectItem value="user">User-specific</SelectItem>
                  <SelectItem value="public">Public</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {scope === 'group' && (
              <div className="space-y-2">
                <Label>Authorized Groups</Label>
                <GroupSelector
                  selectedGroups={selectedGroups}
                  onChange={setSelectedGroups}
                />
              </div>
            )}

            {scope === 'user' && (
              <div className="space-y-2">
                <Label>Authorized Users</Label>
                <UserSelector
                  selectedUsers={selectedUsers}
                  onChange={setSelectedUsers}
                />
              </div>
            )}
          </>
        )}

        <div className="flex justify-end">
          <Button onClick={handleSave} disabled={saving}>
            {saving ? "Saving..." : "Save Access Rules"}
          </Button>
        </div>

        <div className="text-sm text-muted-foreground">
          <p><strong>Note:</strong> Admin users always have access to all knowledge bases.</p>
        </div>
      </CardContent>
    </Card>
  );
}
