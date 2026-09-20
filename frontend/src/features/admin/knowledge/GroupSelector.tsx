// Group Selector Component
import { useState, useEffect } from "react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { X } from "lucide-react";
import { apiRequest } from "@/api/request";

interface Group {
  id: string;
  name: string;
  description?: string;
  enabled: boolean;
}

interface GroupSelectorProps {
  selectedGroups: string[];
  onChange: (groups: string[]) => void;
}

export function GroupSelector({ selectedGroups, onChange }: GroupSelectorProps) {
  const [groups, setGroups] = useState<Group[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadGroups = async () => {
      try {
        const response = await apiRequest('/api/admin/groups');
        const data = await response.json();
        setGroups(data.groups || []);
      } catch (error) {
        console.error("Failed to load groups:", error);
      } finally {
        setLoading(false);
      }
    };

    loadGroups();
  }, []);

  const handleAddGroup = (groupId: string) => {
    if (!selectedGroups.includes(groupId)) {
      onChange([...selectedGroups, groupId]);
    }
  };

  const handleRemoveGroup = (groupId: string) => {
    onChange(selectedGroups.filter(id => id !== groupId));
  };

  if (loading) {
    return <div className="text-sm text-muted-foreground">Loading groups...</div>;
  }

  return (
    <div className="space-y-2">
      <Select onValueChange={handleAddGroup}>
        <SelectTrigger>
          <SelectValue placeholder="Select a group to add" />
        </SelectTrigger>
        <SelectContent>
          {groups
            .filter(g => g.enabled && !selectedGroups.includes(g.id))
            .map((group) => (
              <SelectItem key={group.id} value={group.id}>
                {group.name} ({group.id})
              </SelectItem>
            ))}
          {groups.filter(g => g.enabled && !selectedGroups.includes(g.id)).length === 0 && (
            <SelectItem value="none" disabled>
              No available groups
            </SelectItem>
          )}
        </SelectContent>
      </Select>

      {selectedGroups.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {selectedGroups.map((groupId) => {
            const group = groups.find(g => g.id === groupId);
            return (
              <Badge key={groupId} variant="default" className="gap-1">
                {group?.name || groupId}
                <button
                  onClick={() => handleRemoveGroup(groupId)}
                  className="ml-1 hover:bg-white/20 rounded-full p-0.5"
                >
                  <X className="h-3 w-3" />
                </button>
              </Badge>
            );
          })}
        </div>
      )}
    </div>
  );
}
